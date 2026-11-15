# Traceability: SRS → spec → code → tests

Generated from [`specs/fleet-monitor.md`](../specs/fleet-monitor.md) and the test files on 2026-11-15, at the end of V1.
`tests/test_docs.py::test_req_traceability_lists_every_req` checks that every REQ in the spec is in this table, that every test
named here exists, and that every `test_req_<id>_...` test is in its REQ's row.

**41 REQs: 30 Done, 9 Partial, 2 Replaced.** Code files for each REQ are listed in the spec under the same id.

**Why the Partial ones are partial.** Six REQs touched by V1 have a part that must run on GCP: the images built by Cloud Build
(REQ-023), the bridge container (REQ-027), the internal load balancer (REQ-032), the Dataflow job (REQ-033), the replay against
the real router (REQ-036) and the Jenkins stages (REQ-037). That code is written and tested offline (manifest
validator, tests that read the deploy files, the Dataflow entry point run end to end on Beam's local streaming runner), but the GCP
project the deployment runs in could not be reached from the machine V1 was built on, so it has not run there. The plan's cut line
says to mark these Partial rather than drop them. Three MVP REQs stay Partial for reasons recorded in the spec (DV-7, DV-8, FR-11).

| REQ | Title | SRS | Status | Tests | Notes and evidence |
|---|---|---|---|---|---|
| REQ-001 | Simulated fleet | FR-1, NFR-7 | **Done** | `test_every_van_gets_its_own_agent_and_port`, `test_route_geometry`, `test_tick_writes_all_signals`, `test_trips_complete` |  |
| REQ-002 | Digital twin in Kuksa (VSS) | FR-2 | **Done** | `test_overlay_allows_every_hazard_type`, `test_overlay_defines_every_custom_path` |  |
| REQ-003 | Twin signals updated | FR-3 | **Done** | `test_battery_drains_while_driving`, `test_tick_writes_all_signals` |  |
| REQ-004 | Hazard rules | FR-4 | **Done** | `test_energy_and_coolant`, `test_harsh_and_severe_braking`, `test_most_severe_wins`, `test_normal_driving_has_no_hazard`, `test_overspeed_uses_route_limit_plus_margin`, `test_traction_loss_needs_minimum_speed` |  |
| REQ-005 | Hazard detector | FR-4, FR-5, NFR-1 | **Done** | `test_hazard_is_written_back_with_t0`, `test_hold_window_then_clear`, `test_waits_for_frame_to_settle` |  |
| REQ-006 | Cloud publisher | FR-5, FR-7 | **Done** | `test_hazard_active_before_start_is_not_resent`, `test_hazard_event_is_sent_once` |  |
| REQ-007 | Vehicle-to-cloud contract | FR-7, NFR-7 | **Done** | `test_req_007_hazard_event_has_trip_id`, `test_req_007_hazard_trip_id_is_optional_for_readers`, `test_req_007_messages_match_json_schemas`, `test_req_007_schemas_reject_unknown_fields_and_wrong_types`, `test_snapshot_shape` | changed in V1: `trip_id` in hazard events, JSON Schemas |
| REQ-008 | Vehicle software managed by Ankaios | FR-6, NFR-5 | **Partial** | `test_every_van_gets_its_own_agent_and_port`, `test_state_yaml_is_up_to_date`, `test_zenoh_adds_a_publisher_per_van` | no remote update flow (charter Could, Phase 2); checked on the VM in the MVP |
| REQ-009 | Ingestion | FR-8 | **Done** | `test_req_009_malformed_json_is_ignored`, `test_telemetry_updates_twin`, `test_unknown_vehicle_is_discarded` | changed in V1: invalid telemetry rejected; malformed JSON now tested |
| REQ-010 | Storage in PostgreSQL | FR-9 | **Done** | `test_alert_lifecycle`, `test_telemetry_history` | changed in V1: `trips` table replaced by the pipeline tables |
| REQ-011 | Hazard latency | NFR-1 | **Done** | `test_hazard_creates_alert_with_latency`, `test_hazard_reaches_cloud_within_two_seconds`, `test_latency_stats` | laptop re-measured in V1: p95 149 ms over 78 hazards; GCP figures from the MVP; README latency results; `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-012 | Alert lifecycle | FR-15 | **Done** | `test_alert_lifecycle`, `test_hazard_flows_to_alerts_and_can_be_acked` |  |
| REQ-013 | Cloud-side rules | FR-11 | **Partial** | `test_offline_then_back_online`, `test_req_013_energy_drop_alert` | FR-11 beyond two live rules is V2; `ENERGY_DROP` now tested |
| REQ-014 | Trip tracking and route summary in CloudService | FR-12, FR-16 | **Replaced** | no automated test | by REQ-031, REQ-032, REQ-034 (T11) |
| REQ-015 | REST API and WebSocket | FR-14, FR-15, FR-16 | **Done** | `test_hazard_flows_to_alerts_and_can_be_acked`, `test_health_and_fleet`, `test_websocket_sends_snapshot_then_live_twin` |  |
| REQ-016 | Live map | FR-14, NFR-3 | **Done** | no automated test | checked by hand in the browser; `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-017 | Fleet panel | FR-3, FR-16, NFR-3 | **Done** | no automated test | checked by hand in the browser; `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-018 | Alerts panel | FR-15, NFR-3 | **Done** | no automated test | checked by hand in the browser |
| REQ-019 | Latency panel | NFR-1 | **Done** | no automated test | checked by hand in the browser; `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-020 | Route performance panel | FR-16 | **Replaced** | no automated test | by REQ-034 (new columns, flagged records, pipeline status) |
| REQ-021 | CI on GitHub Actions | FR-19, NFR-6 | **Done** | no automated test | GitHub Actions runs on PRs #1-#10 |
| REQ-022 | CD with Jenkins on GKE | FR-18, NFR-6 | **Done** | no automated test | MVP stages; the V1 stages are in REQ-037; Jenkins build history, `deployments` table |
| REQ-023 | Containers and dependencies | NFR-4 | **Partial** | `test_req_023_only_vehicle_code_imports_kuksa_client`, `test_req_023_requirements_are_split` | AC3: both requirement sets install in fresh venvs; the images are not built yet (no Docker here; Cloud Build builds them on the next deploy) |
| REQ-024 | Integration test | FR-19 | **Partial** | `test_hazard_reaches_cloud_within_two_seconds` | the integration test uses the fakes (DV-7) |
| REQ-025 | One-command demo | FR-1, NFR-3 | **Done** | no automated test |  |
| REQ-026 | Latency test tool | rubric / charter | **Done** | no automated test | README latency results |
| REQ-027 | Pub/Sub bridge | FR-8 | **Partial** | `test_req_027_attributes`, `test_req_027_bridge_container_in_the_cloud_pod`, `test_req_027_bridge_waits_for_pubsub_instead_of_crashing`, `test_req_027_buffer_keeps_last_hour`, `test_req_027_payload_is_copied_unchanged`, `test_req_027_publish_failure_does_not_stop_bridge` | AC1-AC3 done; AC4 (bridge container on GKE) not run on GCP: the deployment's project was not reachable from the machine V1 was built on |
| REQ-028 | Shared quality check validate() | FR-10, NFR-2 | **Done** | `test_req_028_a_value_that_is_not_a_number_is_out_of_range`, `test_req_028_hazard_location_out_of_range`, `test_req_028_late`, `test_req_028_missing_hazard_field`, `test_req_028_missing_telemetry_field`, `test_req_028_odometer_cannot_be_negative`, `test_req_028_out_of_range`, `test_req_028_reports_every_problem_with_its_field`, `test_req_028_unknown_kind_is_an_error`, `test_req_028_unknown_vehicle`, `test_req_028_valid_messages_have_no_problems` | new in V1 |
| REQ-029 | The live path rejects invalid telemetry | FR-10, NFR-2 | **Done** | `test_req_029_hazard_with_problem_still_alerts`, `test_req_029_invalid_telemetry_does_not_update_twin`, `test_req_029_invalid_telemetry_is_not_stored`, `test_req_029_partial_message_then_full_message` | new in V1 |
| REQ-030 | Beam: quality flags | FR-10, NFR-2 | **Done** | `test_req_030_malformed_message_is_flagged`, `test_req_030_one_flag_per_bad_record` | new in V1 |
| REQ-031 | Beam: trip and route efficiency and safety | FR-12 | **Done** | `test_req_031_charging_is_not_energy_used`, `test_req_031_exactly_2_kmh_is_moving_not_stopped`, `test_req_031_first_trip_seen_and_trip_in_progress_are_left_out`, `test_req_031_no_records_no_trips`, `test_req_031_records_out_of_order_are_sorted_by_time`, `test_req_031_sample_trip_matches_hand_computed_values`, `test_req_031_second_run_changes_nothing`, `test_req_031_streaming_mode_writes_the_same_rows`, `test_req_031_trip_rows_match_metrics`, `test_req_031_zero_distance_trip_has_no_rates` | new in V1; AC4: `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-032 | Pipeline tables | FR-9 | **Partial** | `test_req_032_fleet_db_has_an_internal_service_for_dataflow`, `test_req_032_quality_flag_is_stored_once`, `test_req_032_route_stats_view_sums_trips`, `test_req_032_store_for_returns_the_registered_store`, `test_req_032_trip_upsert_keeps_one_row_per_trip` | AC1-AC3 done (SQLite and PostgreSQL 16); AC4 (internal load balancer) not run on GCP: the deployment's project was not reachable from the machine V1 was built on; PostgreSQL run: `docs/reviews/v1-phase-a-e.md` |
| REQ-033 | Runners | rubric / charter | **Partial** | `test_req_033_batch_run_writes_tables`, `test_req_033_live_path_works_without_pipeline`, `test_req_033_missing_publish_time_falls_back_to_now`, `test_req_033_pubsub_publish_time_is_the_arrival_time`, `test_req_033_streaming_entry_reads_both_subscriptions` | AC1, AC2, AC4 done; AC3 (Dataflow) tested end to end on the local streaming runner but not run on GCP: the deployment's project was not reachable from the machine V1 was built on (plan cut line) |
| REQ-036 | Sample data and replay | FR-10 | **Partial** | `test_req_036_every_line_gives_its_expected_problems`, `test_req_036_replay_reaches_both_paths`, `test_req_036_running_fleet_gets_only_the_bad_records`, `test_req_036_sample_covers_every_problem_code`, `test_req_036_sample_hazards_do_not_distort_latency`, `test_req_036_times_are_relative_to_now` | AC1, AC2, AC2a, AC4 done; AC3 against the real Zenoh router not run on GCP: the deployment's project was not reachable from the machine V1 was built on |
| REQ-041 | Pipeline documentation | rubric / charter | **Done** | no automated test | new in V1; `docs/pipeline.md` |
| REQ-034 | Route report | FR-12, FR-16, NFR-3 | **Done** | `test_req_034_flagged_count_and_pipeline_status`, `test_req_034_routes_read_route_stats`, `test_req_034_trips_read_trip_stats` | new in V1; `docs/evidence/v1-laptop-route-report.jpg` |
| REQ-035 | Delivery stops | FR-1, FR-12 | **Done** | `test_req_035_route_b_stops_longest`, `test_req_035_same_seed_same_stops`, `test_req_035_stop_does_not_cause_harsh_braking`, `test_req_035_van_drives_on_after_a_stop` | new in V1 |
| REQ-038 | Health reflects the database | NFR-6 | **Done** | `test_req_038_health_ok_when_database_answers`, `test_req_038_health_returns_503_when_database_is_down` | new in V1 |
| REQ-037 | Pipeline deployment | FR-18, NFR-6 | **Partial** | `test_req_037_dataflow_never_starts_on_a_merge`, `test_req_037_drain_all`, `test_req_037_jenkins_creates_the_topics_and_subscriptions_the_code_uses`, `test_req_037_machine_type_can_be_changed`, `test_req_037_pubsub_stage_cannot_stop_the_deploy`, `test_req_037_start_args`, `test_req_037_start_refuses_when_running` | code, Jenkins stages and docs done and tested offline; the stages and a real start/drain not run on GCP: the deployment's project was not reachable from the machine V1 was built on |
| REQ-039 | Tests run on Windows | NFR-4 | **Done** | no automated test | new in V1; fresh-venv run on Windows (dev log, T01) |
| REQ-040 | Docstrings match the code | NFR-4 | **Done** | `test_req_040_dead_code_is_gone`, `test_req_040_no_outdated_next_phase_notes` | new in V1 |
