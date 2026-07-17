import io
import tempfile
import unittest
from unittest.mock import patch

import server


class StructuredErrorTests(unittest.TestCase):
    def test_tool_error_omits_details_when_absent(self):
        result = server._tool_error(
            "not_logged_in",
            "ArtCraft is not signed in.",
            "Open ArtCraft and sign in.",
        )

        self.assertEqual(result, {
            "ok": False,
            "error_code": "not_logged_in",
            "message": "ArtCraft is not signed in.",
            "remediation": "Open ArtCraft and sign in.",
        })

    def test_tool_error_includes_sanitized_details(self):
        result = server._tool_error(
            "backend_unavailable",
            "ArtCraft request failed.",
            "Retry shortly.",
            {"http_status": 503},
        )

        self.assertEqual(result["details"], {"http_status": 503})

    def test_safe_api_error_maps_unauthorized_without_leaking_response(self):
        error = server.urllib.error.HTTPError(
            "https://api.storyteller.ai/private",
            401,
            "cookie=session-secret-value",
            None,
            None,
        )

        result = server._safe_api_error(error)

        self.assertEqual(result["error_code"], "session_expired")
        self.assertEqual(result["details"], {"http_status": 401})
        self.assertNotIn("session-secret-value", str(result))

    def test_safe_api_error_maps_server_and_network_failures(self):
        server_error = server._safe_api_error(server.ArtCraftHTTPError(503))
        network_error = server._safe_api_error(server.urllib.error.URLError("offline"))

        self.assertEqual(server_error["error_code"], "backend_unavailable")
        self.assertEqual(server_error["details"], {"http_status": 503})
        self.assertEqual(network_error["error_code"], "backend_unavailable")
        self.assertNotIn("details", network_error)

    def test_http_json_preserves_status_without_response_body(self):
        http_error = server.urllib.error.HTTPError(
            "https://api.storyteller.ai/private",
            401,
            "Unauthorized",
            None,
            io.BytesIO(b"session-secret-value"),
        )
        with patch.object(server.urllib.request, "urlopen", side_effect=http_error):
            with self.assertRaises(server.ArtCraftHTTPError) as raised:
                server._http_json("GET", "/private")

        self.assertEqual(raised.exception.code, 401)
        self.assertNotIn("session-secret-value", str(raised.exception))


class CookieParsingTests(unittest.TestCase):
    def test_cookie_domain_accepts_storyteller_host_only(self):
        self.assertTrue(server._cookie_domain_matches({"HostOnly": "api.storyteller.ai"}))

    def test_cookie_domain_accepts_storyteller_suffix(self):
        self.assertTrue(server._cookie_domain_matches({"Suffix": "storyteller.ai"}))

    def test_parse_cookie_name_value_rejects_malformed_entries(self):
        self.assertIsNone(server._parse_cookie_name_value("not-a-cookie"))
        self.assertIsNone(server._parse_cookie_name_value("visitor="))
        self.assertIsNone(server._parse_cookie_name_value(123))

    def test_cookie_header_ignores_same_named_cookie_from_unrelated_domain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_store = server.Path(temp_dir) / "cookies.json"
            cookie_store.write_text(server.json.dumps([
                {
                    "raw_cookie": "visitor=wrong-domain-secret; Path=/",
                    "domain": {"HostOnly": "unrelated.example"},
                },
                {
                    "raw_cookie": "session=correct-session; Path=/",
                    "domain": {"HostOnly": "api.storyteller.ai"},
                },
            ]))
            with patch.object(server, "_tauri_cookie_store", return_value=cookie_store), \
                 patch.object(server, "_credentials_dir", return_value=server.Path(temp_dir) / "missing"):
                header = server._storyteller_cookie_header()

        self.assertEqual(header, "session=correct-session")
        self.assertNotIn("wrong-domain-secret", header)

    def test_credential_status_never_returns_cookie_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_store = server.Path(temp_dir) / "cookies.json"
            cookie_store.write_text(server.json.dumps([{
                "raw_cookie": "visitor=visitor-secret; Path=/",
                "domain": {"Suffix": "storyteller.ai"},
            }]))
            with patch.object(server, "_tauri_cookie_store", return_value=cookie_store), \
                 patch.object(server, "_credentials_dir", return_value=server.Path(temp_dir) / "credentials"):
                result = server.artcraft_credential_status()
        self.assertTrue(result["has_artcraft_subscription_cookies"])
        self.assertNotIn("visitor-secret", str(result))


class UserStatusTests(unittest.TestCase):
    def test_user_status_returns_credit_and_subscription_summary(self):
        credits = {
            "success": True,
            "free_credits": 2,
            "monthly_credits": 100,
            "banked_credits": 25,
            "sum_total_credits": 127,
        }
        subscription = {
            "success": True,
            "active_subscription": {
                "subscription_token": "subscription-secret",
                "namespace": "artcraft",
                "product_slug": "creator",
                "next_bill_at": "2026-08-01T00:00:00Z",
                "subscription_end_at": None,
            },
        }
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", side_effect=[credits, subscription]):
            result = server.artcraft_get_user_status()

        self.assertEqual(result, {
            "ok": True,
            "credits": {"free": 2, "monthly": 100, "banked": 25, "total": 127},
            "subscription": {
                "product_slug": "creator",
                "next_bill_at": "2026-08-01T00:00:00Z",
                "subscription_end_at": None,
            },
        })
        self.assertNotIn("subscription-secret", str(result))

    def test_user_status_reports_missing_login(self):
        with patch.object(server, "_storyteller_cookie_header", return_value=None):
            result = server.artcraft_get_user_status()
        self.assertEqual(result["error_code"], "not_logged_in")

    def test_user_status_sanitizes_endpoint_failure(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", side_effect=server.ArtCraftHTTPError(503)):
            result = server.artcraft_get_user_status()
        self.assertEqual(result["error_code"], "backend_unavailable")
        self.assertEqual(result["details"], {"http_status": 503})


class AspectRatioAliasTests(unittest.TestCase):
    def test_aspect_ratio_friendly_alias_maps_to_serde_variant(self):
        self.assertEqual(server._resolve_aspect_ratio("16:9"), "wide_sixteen_by_nine")
        self.assertEqual(server._resolve_aspect_ratio("1:1"), "square")
        self.assertEqual(server._resolve_aspect_ratio("21:9"), "wide_twenty_one_by_nine")

    def test_aspect_ratio_passes_through_unknown_serde_variants(self):
        self.assertEqual(server._resolve_aspect_ratio("wide_sixteen_by_nine"), "wide_sixteen_by_nine")
        self.assertEqual(server._resolve_aspect_ratio(None), None)


class HealthCheckTests(unittest.TestCase):
    def test_health_check_reports_valid_session(self):
        with patch.object(server, "_is_artcraft_installed", return_value=True), \
             patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value={"success": True}):
            result = server.artcraft_check_connection()

        self.assertEqual(result, {
            "status": "ok",
            "desktop_app_installed": True,
            "signed_in": True,
            "session_valid": True,
            "error_code": None,
            "remediation": None,
        })

    def test_health_check_distinguishes_not_installed(self):
        with patch.object(server, "_is_artcraft_installed", return_value=False), \
             patch.object(server, "_storyteller_cookie_header", return_value=None):
            result = server.artcraft_check_connection()
        self.assertEqual(result["status"], "not_installed")

    def test_health_check_distinguishes_not_logged_in(self):
        with patch.object(server, "_is_artcraft_installed", return_value=True), \
             patch.object(server, "_storyteller_cookie_header", return_value=None):
            result = server.artcraft_check_connection()
        self.assertEqual(result["status"], "not_logged_in")

    def test_health_check_distinguishes_invalid_session(self):
        with patch.object(server, "_is_artcraft_installed", return_value=True), \
             patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", side_effect=server.ArtCraftHTTPError(401)):
            result = server.artcraft_check_connection()
        self.assertEqual(result["status"], "session_invalid")
        self.assertFalse(result["session_valid"])

    def test_health_check_distinguishes_backend_failure(self):
        with patch.object(server, "_is_artcraft_installed", return_value=True), \
             patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", side_effect=server.urllib.error.URLError("offline")):
            result = server.artcraft_check_connection()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "backend_unavailable")


class PollingTests(unittest.TestCase):
    def test_image_wait_polls_silently_every_five_seconds_by_default(self):
        pending = {
            "found": True,
            "ready": False,
            "task_status": "pending",
            "model_type": "gpt_image_2",
            "inference_category": "image_generation",
            "provider_job_id": "jinf_test",
        }
        complete = {
            **pending,
            "ready": True,
            "task_status": "complete_success",
            "output_count": 1,
        }
        with patch.object(server, "_get_subscription_job_result", side_effect=[pending, complete]), \
             patch.object(server.time, "sleep") as sleep:
            result = server.artcraft_wait_for_result("jinf_test", timeout_seconds=20)

        self.assertTrue(result["ready"])
        sleep.assert_called_once_with(5)

    def test_wait_timeout_preserves_job_token_and_is_resumable(self):
        pending = {
            "found": True,
            "ready": False,
            "task_status": "pending",
            "provider_job_id": "jinf_resume_me",
        }
        with patch.object(server, "_get_subscription_job_result", return_value=pending), \
             patch.object(server.time, "time", side_effect=[0, 0, 10]), \
             patch.object(server.time, "sleep"):
            result = server.artcraft_wait_for_result("jinf_resume_me", timeout_seconds=10)

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["provider_job_id"], "jinf_resume_me")
        self.assertEqual(result["task_status"], "pending")
        self.assertEqual(result["error_code"], "generation_timeout")
        self.assertIn("artcraft_get_task_result", result["remediation"])

    def test_video_wait_uses_slower_default_poll_interval(self):
        pending = {
            "found": True,
            "ready": False,
            "task_status": "pending",
            "inference_category": "video_generation",
            "provider_job_id": "jinf_video",
        }
        complete = {**pending, "ready": True, "task_status": "complete_success"}
        with patch.object(server, "_get_subscription_job_result", side_effect=[pending, complete]), \
             patch.object(server.time, "sleep") as sleep:
            result = server.artcraft_wait_for_result("jinf_video")

        self.assertTrue(result["ready"])
        sleep.assert_called_once_with(20)

    def test_terminal_failure_stops_without_sleeping(self):
        failed = {
            "found": True,
            "ready": False,
            "task_status": "complete_failure",
            "provider_job_id": "jinf_failed",
        }
        with patch.object(server, "_get_subscription_job_result", return_value=failed), \
             patch.object(server.time, "sleep") as sleep:
            result = server.artcraft_wait_for_result("jinf_failed")
        self.assertEqual(result["task_status"], "complete_failure")
        sleep.assert_not_called()


class ReferenceUploadTests(unittest.TestCase):
    def test_existing_media_token_passes_through_without_network(self):
        with patch.object(server.urllib.request, "urlopen") as urlopen:
            result = server.artcraft_upload_reference_image("m_existing123")

        self.assertEqual(result, {
            "ok": True,
            "media_token": "m_existing123",
            "uploaded": False,
            "source_type": "existing_media_token",
            "is_intermediate_system_file": True,
        })
        urlopen.assert_not_called()

    def test_missing_local_reference_returns_structured_error(self):
        result = server.artcraft_upload_reference_image("/definitely/missing/reference.png")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "reference_image_failed")

    def test_load_reference_bytes_reads_local_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "reference.png"
            image_bytes = b"\x89PNG\r\n\x1a\nmock-image"
            path.write_bytes(image_bytes)

            loaded, mime_type, filename = server._load_reference_bytes(str(path), 1024)

        self.assertEqual(loaded, image_bytes)
        self.assertEqual(mime_type, "image/png")
        self.assertEqual(filename, "reference.png")

    def test_load_reference_bytes_downloads_https_png(self):
        image_bytes = b"\x89PNG\r\n\x1a\nremote-image"
        response = io.BytesIO(image_bytes)
        with patch.object(server.urllib.request, "urlopen", return_value=response) as urlopen:
            loaded, mime_type, filename = server._load_reference_bytes(
                "https://example.com/reference.png",
                1024,
            )

        self.assertEqual(loaded, image_bytes)
        self.assertEqual(mime_type, "image/png")
        self.assertEqual(filename, "reference.png")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/reference.png")

    def test_upload_local_reference_uses_hidden_intermediate_file_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "reference.png"
            image_bytes = b"\x89PNG\r\n\x1a\nmock-image"
            path.write_bytes(image_bytes)
            with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
                 patch.object(
                     server,
                     "_http_multipart_image_upload",
                     return_value={"success": True, "media_file_token": "m_uploaded"},
                 ) as upload:
                result = server.artcraft_upload_reference_image(str(path))

        self.assertEqual(result, {
            "ok": True,
            "media_token": "m_uploaded",
            "uploaded": True,
            "source_type": "local_file",
            "is_intermediate_system_file": True,
        })
        upload.assert_called_once_with(
            image_bytes,
            "image/png",
            "reference.png",
            "session=test",
            True,
        )

    def test_reference_loader_rejects_plain_http(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            server._load_reference_bytes("http://example.com/reference.png", 1024)

    def test_reference_loader_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "large.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n12345")
            with self.assertRaisesRegex(ValueError, "max_bytes"):
                server._load_reference_bytes(str(path), 8)

    def test_reference_loader_rejects_unsupported_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "reference.webp"
            path.write_bytes(b"RIFFmockWEBP")
            with self.assertRaisesRegex(ValueError, "PNG, JPEG, or GIF"):
                server._load_reference_bytes(str(path), 1024)

    def test_multipart_upload_uses_exact_endpoint_and_fields(self):
        response = io.BytesIO(b'{"success":true,"media_file_token":"m_uploaded"}')
        with patch.object(server.urllib.request, "urlopen", return_value=response) as urlopen:
            result = server._http_multipart_image_upload(
                b"\x89PNG\r\n\x1a\nmock",
                "image/png",
                "reference.png",
                "session=session-secret",
                True,
            )

        request = urlopen.call_args.args[0]
        body = request.data.decode("latin-1")
        self.assertEqual(request.full_url, f"{server.ARTCRAFT_API}/v1/media_files/upload/image")
        self.assertEqual(request.get_header("Cookie"), "session=session-secret")
        self.assertIn('name="uuid_idempotency_token"', body)
        self.assertIn('name="file"; filename="reference.png"', body)
        self.assertIn("Content-Type: image/png", body)
        self.assertIn('name="is_intermediate_system_file"', body)
        self.assertIn("\r\n\r\ntrue\r\n", body)
        self.assertNotIn("session-secret", str(result))


class AudioVideoReferenceUploadTests(unittest.TestCase):
    def test_reference_media_mime_identifies_aac(self):
        self.assertEqual(
            server._reference_media_mime_type(b"\xff\xf1\x50\x80mock-audio", "voice.aac", "audio"),
            "audio/aac",
        )

    def test_audio_upload_uses_audio_endpoint_without_hidden_file_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "voice.mp3"
            audio_bytes = b"ID3\x04\x00\x00mock-audio"
            path.write_bytes(audio_bytes)
            with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
                 patch.object(server, "_http_multipart_media_upload", return_value={"success": True, "media_file_token": "m_audio"}) as upload:
                result = server.artcraft_upload_reference_audio(str(path))

        self.assertEqual(result, {
            "ok": True,
            "media_token": "m_audio",
            "uploaded": True,
            "source_type": "local_file",
            "media_kind": "audio",
        })
        upload.assert_called_once_with(
            "/v1/media_files/upload/audio",
            audio_bytes,
            "audio/mpeg",
            "voice.mp3",
            "session=test",
            None,
        )

    def test_video_upload_uses_new_video_endpoint_and_hidden_file_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = server.Path(temp_dir) / "motion.mp4"
            video_bytes = b"\x00\x00\x00\x18ftypisommock-video"
            path.write_bytes(video_bytes)
            with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
                 patch.object(server, "_http_multipart_media_upload", return_value={"success": True, "media_file_token": "m_video"}) as upload:
                result = server.artcraft_upload_reference_video(str(path))

        self.assertEqual(result, {
            "ok": True,
            "media_token": "m_video",
            "uploaded": True,
            "source_type": "local_file",
            "media_kind": "video",
            "is_intermediate_system_file": True,
        })
        upload.assert_called_once_with(
            "/v1/media_files/upload/new_video",
            video_bytes,
            "video/mp4",
            "motion.mp4",
            "session=test",
            True,
        )


class GenerationInputTests(unittest.TestCase):
    def test_video_generation_preserves_audio_reference_token_order(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value={"inference_job_token": "jinf_test"}) as http_json:
            server.artcraft_generate_video_subscription(
                "test prompt",
                reference_audio_media_tokens="m_first, m_second,m_third",
                insert_into_artcraft_task_db=False,
            )

        body = http_json.call_args.args[2]
        self.assertEqual(body["reference_audio_media_tokens"], ["m_first", "m_second", "m_third"])

    def test_image_generation_preserves_reference_token_order(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value={"inference_job_token": "jinf_test"}) as http_json:
            server.artcraft_generate_image_subscription(
                "test prompt",
                "gpt_image_2",
                reference_image_media_tokens="m_first, m_second,m_third",
                insert_into_artcraft_task_db=False,
            )
        body = http_json.call_args.args[2]
        self.assertEqual(body["image_media_tokens"], ["m_first", "m_second", "m_third"])


class BatchResultTests(unittest.TestCase):
    def test_list_batch_outputs_is_media_type_agnostic(self):
        api_response = {
            "success": True,
            "media_files": [
                {
                    "token": "m_image",
                    "media_class": "image",
                    "media_type": "png",
                    "media_links": {
                        "cdn_url": "https://cdn.example/image.png",
                        "maybe_thumbnail_template": "https://cdn.example/image-{WIDTH}.png",
                        "maybe_video_previews": None,
                    },
                    "created_at": "2026-01-01T00:00:00Z",
                },
                {
                    "token": "m_video",
                    "media_class": "video",
                    "media_type": "mp4",
                    "media_links": {
                        "cdn_url": "https://cdn.example/video.mp4",
                        "maybe_thumbnail_template": None,
                        "maybe_video_previews": ["https://cdn.example/preview.gif"],
                    },
                    "created_at": "2026-01-01T00:00:01Z",
                },
            ],
        }
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value=api_response) as http_json:
            outputs = server._list_batch_outputs("batch_g_test")

        self.assertEqual([item["media_class"] for item in outputs], ["image", "video"])
        self.assertEqual(outputs[1]["cdn_url"], "https://cdn.example/video.mp4")
        http_json.assert_called_once_with(
            "GET",
            "/v1/media_files/batch_gen_redux/batch_g_test",
            cookie="session=test",
        )

    def test_completed_batch_is_expanded_while_primary_fields_remain(self):
        job = {
            "job_token": "jinf_test",
            "status": {"status": "complete_success"},
            "request": {
                "maybe_model_type": "gpt_image_2",
                "inference_category": "image_generation",
            },
            "maybe_result": {
                "entity_token": "m_primary",
                "entity_type": "media_file",
                "maybe_batch_token": "batch_g_test",
                "maybe_successfully_completed_at": "2026-01-01T00:00:02Z",
                "media_links": {"cdn_url": "https://cdn.example/primary.png"},
            },
        }
        expanded = [
            {"media_token": "m_one", "media_class": "image", "cdn_url": "https://cdn.example/1.png"},
            {"media_token": "m_two", "media_class": "image", "cdn_url": "https://cdn.example/2.png"},
        ]
        with patch.object(server, "_resolve_provider_job_id", return_value=("jinf_test", None)), \
             patch.object(server, "_list_subscription_jobs", return_value=[job]), \
             patch.object(server, "_list_batch_outputs", return_value=expanded):
            result = server._get_subscription_job_result("jinf_test")

        self.assertTrue(result["ready"])
        self.assertEqual(result["cdn_url"], "https://cdn.example/primary.png")
        self.assertEqual(result["media_token"], "m_primary")
        self.assertEqual(result["output_count"], 2)
        self.assertEqual(result["outputs"], expanded)

    def test_single_output_gets_uniform_outputs_array(self):
        response = {
            "ready": True,
            "media_token": "m_single",
            "media_class": "video",
            "cdn_url": "https://cdn.example/single.mp4",
            "video_previews": ["https://cdn.example/preview.gif"],
            "completed_at": "2026-01-01T00:00:00Z",
            "batch_token": None,
        }
        result = server._expand_subscription_outputs(response)
        self.assertEqual(result["output_count"], 1)
        self.assertEqual(result["outputs"][0]["media_token"], "m_single")
        self.assertEqual(result["outputs"][0]["media_class"], "video")



class SeedanceModelRegistryTests(unittest.TestCase):
    def test_registry_contains_nine_seedance_two_p_zero_variants(self):
        ids = set(server.SEEDANCE_2P0_MODELS)
        expected = {
            "seedance_2p0",
            "seedance_2p0_fast",
            "seedance_2p0_bp",
            "seedance_2p0_bp_fast",
            "seedance_2p0_bpu",
            "seedance_2p0_bpu_fast",
            "seedance_2p0_mini",
            "seedance_2p0_bp_mini",
            "seedance_2p0_bpu_mini",
        }
        self.assertEqual(ids, expected)

    def test_registry_maps_each_id_to_a_full_name(self):
        for model_id, entry in server.SEEDANCE_2P0_MODELS.items():
            self.assertEqual(entry["model"], model_id)
            self.assertTrue(entry["full_name"])

    def test_plus_ultra_is_flagged_as_bytedance_real_model(self):
        self.assertTrue(server.SEEDANCE_2P0_MODELS["seedance_2p0_bpu"]["is_bytedance_real_model"])
        self.assertTrue(server.SEEDANCE_2P0_MODELS["seedance_2p0_bpu_mini"]["is_bytedance_real_model"])
        self.assertFalse(server.SEEDANCE_2P0_MODELS["seedance_2p0"]["is_bytedance_real_model"])
        self.assertFalse(server.SEEDANCE_2P0_MODELS["seedance_2p0_mini"]["is_bytedance_real_model"])


class ListVideoModelsTests(unittest.TestCase):
    def _sample_family(self):
        return {
            "success": True,
            "models": [
                {"model": "seedance_2p0", "model_creator": "bytedance",
                 "full_name": "Seedance 2.0", "text_prompt_supported": True,
                 "starting_keyframe_supported": True, "ending_keyframe_supported": True,
                 "image_references_supported": True, "image_references_max": 9,
                 "audio_references_supported": True, "aspect_ratio_default": "wide_sixteen_by_nine",
                 "aspect_ratio_options": ["wide_sixteen_by_nine", "square", "tall_nine_by_sixteen"],
                 "resolution_default": "seven_twenty_p",
                 "resolution_options": ["four_eighty_p", "seven_twenty_p", "four_k"],
                 "duration_seconds_default": 5, "duration_seconds_min": 4,
                 "duration_seconds_max": 15, "batch_size_default": 1,
                 "batch_size_options": [1, 2, 4]},
                {"model": "seedance_2p0_bpu", "model_creator": "bytedance",
                 "full_name": "Seedance 2.0 Plus Ultra", "text_prompt_supported": True,
                 "starting_keyframe_supported": True, "ending_keyframe_supported": True,
                 "image_references_supported": True, "image_references_max": 9,
                 "audio_references_supported": True, "aspect_ratio_default": "wide_sixteen_by_nine",
                 "resolution_default": "seven_twenty_p", "duration_seconds_default": 5,
                 "batch_size_default": 1},
                {"model": "grok_imagine_video", "model_creator": "grok",
                 "full_name": "Grok Imagine", "text_prompt_supported": True,
                 "starting_keyframe_supported": True, "image_references_supported": True,
                 "image_references_max": 7, "audio_references_supported": False,
                 "aspect_ratio_default": "wide_sixteen_by_nine",
                 "resolution_default": "seven_twenty_p", "duration_seconds_default": 8,
                 "batch_size_default": 1},
            ],
        }

    def test_list_video_models_returns_seedance_family_with_full_names(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value=self._sample_family()):
            result = server.artcraft_list_video_models()

        self.assertTrue(result["ok"])
        seedance = [m for m in result["models"] if m["is_seedance_2p0"]]
        self.assertEqual(len(seedance), 2)
        self.assertEqual(seedance[0]["model"], "seedance_2p0")
        self.assertEqual(seedance[0]["full_name"], "Seedance 2.0")
        self.assertEqual(seedance[1]["model"], "seedance_2p0_bpu")
        self.assertTrue(seedance[1]["is_bytedance_real_model"])

    def test_list_video_models_carries_capability_flags(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value=self._sample_family()):
            result = server.artcraft_list_video_models()

        entry = next(m for m in result["models"] if m["model"] == "seedance_2p0")
        self.assertTrue(entry["supports_text_prompt"])
        self.assertTrue(entry["supports_starting_keyframe"])
        self.assertTrue(entry["supports_ending_keyframe"])
        self.assertTrue(entry["supports_image_references"])
        self.assertEqual(entry["image_references_max"], 9)
        self.assertEqual(entry["resolution_default"], "seven_twenty_p")

    def test_list_video_models_preserves_every_live_configuration_option(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value=self._sample_family()):
            result = server.artcraft_list_video_models()

        entry = next(m for m in result["models"] if m["model"] == "seedance_2p0")
        self.assertEqual(entry["aspect_ratio_options"], ["wide_sixteen_by_nine", "square", "tall_nine_by_sixteen"])
        self.assertEqual(entry["resolution_options"], ["four_eighty_p", "seven_twenty_p", "four_k"])
        self.assertEqual(entry["duration_seconds_min"], 4)
        self.assertEqual(entry["duration_seconds_max"], 15)
        self.assertEqual(entry["batch_size_options"], [1, 2, 4])

    def test_list_video_models_requires_credentials(self):
        with patch.object(server, "_storyteller_cookie_header", return_value=None):
            result = server.artcraft_list_video_models()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "not_logged_in")

    def test_list_video_models_handles_endpoint_failure(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", side_effect=server.ArtCraftHTTPError(503)):
            result = server.artcraft_list_video_models()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "backend_unavailable")


class VideoCostEstimateTests(unittest.TestCase):
    def test_estimate_video_cost_sends_complete_normalized_configuration(self):
        estimate = {"success": True, "cost_in_credits": 117}
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value=estimate) as http_json:
            result = server.artcraft_estimate_video_cost(
                model="seedance_2p0",
                duration_seconds=15,
                aspect_ratio="16:9",
                resolution="480p",
                video_batch_count=2,
                generate_audio=True,
            )

        self.assertEqual(result, estimate)
        self.assertEqual(http_json.call_args.args[0], "POST")
        self.assertEqual(http_json.call_args.args[1], "/v1/generate/cost_estimate/video")
        body = http_json.call_args.args[2]
        self.assertEqual(body["model"], "seedance_2p0")
        self.assertEqual(body["provider"], "artcraft")
        self.assertEqual(body["generation_mode"], {"type": "text_to_video"})
        self.assertEqual(body["duration_seconds"], 15)
        self.assertEqual(body["aspect_ratio"], "wide_sixteen_by_nine")
        self.assertEqual(body["resolution"], "four_eighty_p")
        self.assertEqual(body["video_batch_count"], 2)
        self.assertTrue(body["generate_audio"])


class VideoModelValidationTests(unittest.TestCase):
    def test_validate_accepts_registry_seedance_variant(self):
        self.assertEqual(server._validate_seedance_model("seedance_2p0_bp"), "seedance_2p0_bp")

    def test_validate_rejects_unknown_seedance_two_p_zero_typo(self):
        self.assertIsNone(server._validate_seedance_model("seedance_2p0_ultra"))

    def test_validate_passthrough_allows_other_video_model(self):
        self.assertEqual(server._validate_seedance_model("grok_imagine_video"), "grok_imagine_video")

    def test_generate_video_rejects_invalid_seedance_typo(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"):
            result = server.artcraft_generate_video_subscription(
                "a prompt", model="seedance_2p0_ultra", insert_into_artcraft_task_db=False,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "invalid_params")
        self.assertIn("seedance_2p0_bpu", result["remediation"])

    def test_generate_video_accepts_plus_ultra_model(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value={"inference_job_token": "jinf_x"}) as http_json:
            server.artcraft_generate_video_subscription(
                "a prompt", model="seedance_2p0_bpu", insert_into_artcraft_task_db=False,
            )
        body = http_json.call_args.args[2]
        self.assertEqual(body["model"], "seedance_2p0_bpu")

    def test_generate_video_default_model_is_seedance_two_p_zero(self):
        with patch.object(server, "_storyteller_cookie_header", return_value="session=test"), \
             patch.object(server, "_http_json", return_value={"inference_job_token": "jinf_x"}) as http_json:
            server.artcraft_generate_video_subscription(
                "a prompt", insert_into_artcraft_task_db=False,
            )
        body = http_json.call_args.args[2]
        self.assertEqual(body["model"], "seedance_2p0")


if __name__ == "__main__":
    unittest.main()
