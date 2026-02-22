def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def create_user(client, email, full_name, cefr_level):
    user_resp = client.post(
        "/api/v1/users",
        json={"email": email, "full_name": full_name, "cefr_level": cefr_level},
    )
    assert user_resp.status_code == 200
    return user_resp.json()["id"]


def auth_headers(client, email):
    token_resp = client.post("/api/v1/auth/token", json={"email": email})
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_user_vocabulary_sessions_flow(client):
    user_id = create_user(client, "student@example.com", "Ivan", "A2")
    headers = auth_headers(client, "student@example.com")

    vocab_resp = client.post(
        "/api/v1/vocabulary",
        json={
            "user_id": user_id,
            "english_lemma": "apple",
            "russian_translation": "яблоко",
            "source_sentence": "I eat an apple",
            "source_url": "https://example.com",
        },
        headers=headers,
    )
    assert vocab_resp.status_code == 200
    assert vocab_resp.json()["context_definition_ru"] is not None
    assert len(vocab_resp.json()["context_definition_ru"]) > 10

    list_vocab = client.get(f"/api/v1/vocabulary?user_id={user_id}", headers=headers)
    assert list_vocab.status_code == 200
    assert len(list_vocab.json()) == 1

    session_resp = client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "яблоко",
                    "is_correct": True,
                },
                {
                    "exercise_id": 2,
                    "prompt": "Translate into Russian: pear",
                    "expected_answer": "груша",
                    "user_answer": "яблоко",
                    "is_correct": False,
                },
            ],
        },
        headers=headers,
    )
    assert session_resp.status_code == 200
    data = session_resp.json()
    assert data["session"]["total"] == 2
    assert data["session"]["correct"] == 1
    assert len(data["incorrect_feedback"]) == 1
    session_id = data["session"]["id"]

    answers_resp = client.get(f"/api/v1/sessions/{session_id}/answers?user_id={user_id}", headers=headers)
    assert answers_resp.status_code == 200
    answers_data = answers_resp.json()
    assert len(answers_data) == 2
    assert answers_data[1]["is_correct"] is False
    assert answers_data[1]["explanation_ru"] is not None

    context_resp = client.get(f"/api/v1/context/{user_id}", headers=headers)
    assert context_resp.status_code == 200
    difficult_words = context_resp.json()["difficult_words"]
    assert "pear" in difficult_words

    rec_resp = client.get(f"/api/v1/context/{user_id}/recommendations?limit=5", headers=headers)
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert "pear" in rec_data["words"]
    assert "pear" in rec_data["recent_error_words"]
    assert "pear" in rec_data["difficult_words"]
    assert "pear" in rec_data["scores"]
    assert rec_data["next_review_at"]["pear"] is not None

    queue_resp = client.get(f"/api/v1/context/{user_id}/review-queue?limit=10", headers=headers)
    assert queue_resp.status_code == 200
    queue_data = queue_resp.json()
    assert queue_data["total_due"] >= 1
    assert len(queue_data["items"]) >= 1
    assert queue_data["items"][0]["word"] == "pear"

    analytics_resp = client.get(f"/api/v1/analytics/progress?user_id={user_id}", headers=headers)
    assert analytics_resp.status_code == 200
    payload = analytics_resp.json()
    assert payload["total_sessions"] == 1
    assert payload["avg_accuracy"] == 0.5


def test_exercise_generation_uses_user_context(client):
    user_id = create_user(client, "learner@example.com", "Anna", "B1")
    headers = auth_headers(client, "learner@example.com")

    client.put(
        f"/api/v1/context/{user_id}",
        json={"cefr_level": "B1", "goals": ["reading"], "difficult_words": ["through"]},
        headers=headers,
    )

    client.post(
        "/api/v1/vocabulary",
        json={
            "user_id": user_id,
            "english_lemma": "through",
            "russian_translation": "через",
        },
        headers=headers,
    )

    response = client.post(
        "/api/v1/exercises/generate",
        json={"user_id": user_id, "size": 1, "mode": "word_scramble", "vocabulary_ids": []},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["exercises"]) == 1
    assert data["exercises"][0]["answer"] == "through"
    assert data["exercises"][0]["exercise_type"] == "word_scramble"
    assert "AI generation used" in data["note"]


def test_exercise_generation_supports_sentence_translation_full_mode(client):
    create_user(client, "mode@example.com", "Mode User", "A2")
    headers = auth_headers(client, "mode@example.com")

    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers,
    )

    response = client.post(
        "/api/v1/exercises/me/generate",
        json={"size": 1, "mode": "sentence_translation_full", "vocabulary_ids": []},
        headers=headers,
    )
    assert response.status_code == 200
    item = response.json()["exercises"][0]
    assert item["exercise_type"] == "sentence_translation_full"
    assert "Translate sentence into Russian:" in item["prompt"]
    assert item["answer"]


def test_exercise_generation_supports_word_definition_match_mode(client):
    create_user(client, "mc@example.com", "MC User", "A2")
    headers = auth_headers(client, "mc@example.com")

    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers,
    )
    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "pear", "russian_translation": "груша"},
        headers=headers,
    )
    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "book", "russian_translation": "книга"},
        headers=headers,
    )
    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "day", "russian_translation": "день"},
        headers=headers,
    )

    response = client.post(
        "/api/v1/exercises/me/generate",
        json={"size": 1, "mode": "word_definition_match", "vocabulary_ids": []},
        headers=headers,
    )
    assert response.status_code == 200
    item = response.json()["exercises"][0]
    assert item["exercise_type"] == "word_definition_match"
    assert "options" in item
    assert len(item["options"]) == 4
    assert "1." in item["prompt"]
    assert "2." in item["prompt"]
    assert "3." in item["prompt"]
    assert "4." in item["prompt"]
    assert item["answer"].startswith("[")


def test_translation_uses_ai_service(client):
    user_id = create_user(client, "translate@example.com", "Petr", "A2")
    headers = auth_headers(client, "translate@example.com")

    response = client.post(
        "/api/v1/translate",
        json={"text": "apple", "user_id": user_id, "source_context": "I eat an apple every day."},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["translated_text"] == "яблоко"
    assert "AI translation used" in data["note"]


def test_translation_prefers_user_glossary_term(client):
    create_user(client, "glossary-translate@example.com", "Glossary User", "B1")
    headers = auth_headers(client, "glossary-translate@example.com")

    add_vocab = client.post(
        "/api/v1/vocabulary/me",
        json={
            "english_lemma": "apple",
            "russian_translation": "яблочко",
            "source_sentence": "She gave me a green apple.",
        },
        headers=headers,
    )
    assert add_vocab.status_code == 200

    response = client.post(
        "/api/v1/translate/me",
        json={"text": "apple", "source_context": "I bought an apple at the market."},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["translated_text"] == "яблочко"


def test_translation_uses_context_to_select_glossary_variant(client):
    create_user(client, "context-translate@example.com", "Context User", "B2")
    headers = auth_headers(client, "context-translate@example.com")

    first = client.post(
        "/api/v1/vocabulary/me",
        json={
            "english_lemma": "book",
            "russian_translation": "книга",
            "source_sentence": "I read this book every evening.",
        },
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/vocabulary/me",
        json={
            "english_lemma": "book",
            "russian_translation": "забронировать",
            "source_sentence": "I want to book a hotel room.",
        },
        headers=headers,
    )
    assert second.status_code == 200

    response = client.post(
        "/api/v1/translate/me",
        json={"text": "book", "source_context": "Please book a hotel for two nights."},
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["translated_text"] == "забронировать"


def test_session_submit_evaluates_correctness_on_server(client):
    create_user(client, "server-eval@example.com", "Eval User", "A2")
    headers = auth_headers(client, "server-eval@example.com")

    response = client.post(
        "/api/v1/sessions/submit",
        json={
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "ЯБЛОКО!!!",
                    "is_correct": False,
                }
            ]
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["correct"] == 1
    assert payload["session"]["accuracy"] == 1
    assert payload["incorrect_feedback"] == []


def test_ai_status_endpoint(client):
    response = client.get("/api/v1/ai/status")
    assert response.status_code == 200
    payload = response.json()
    assert "provider" in payload
    assert "model" in payload
    assert "remote_enabled" in payload
    assert "timeout_seconds" in payload
    assert "max_retries" in payload


def test_auth_token_issue_and_verify(client):
    create_user(client, "auth@example.com", "Auth User", "A2")

    token_resp = client.post("/api/v1/auth/token", json={"email": "auth@example.com"})
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert token_data["access_token"]
    assert token_data["token_type"] == "bearer"

    verify_resp = client.post("/api/v1/auth/verify", json={"token": token_data["access_token"]})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True


def test_auth_login_or_register_creates_then_reuses_user(client):
    first = client.post(
        "/api/v1/auth/login-or-register",
        json={"email": "one-step@example.com", "full_name": "One Step", "cefr_level": "A2"},
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["access_token"]
    assert first_data["is_new_user"] is True
    first_user_id = first_data["user_id"]

    second = client.post(
        "/api/v1/auth/login-or-register",
        json={"email": "one-step@example.com", "full_name": "Ignored Name", "cefr_level": "B2"},
    )
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["access_token"]
    assert second_data["is_new_user"] is False
    assert second_data["user_id"] == first_user_id


def test_study_flow_capture_to_vocabulary_orchestrates_modules(client):
    user_id = create_user(client, "flow@example.com", "Flow User", "A2")
    headers = auth_headers(client, "flow@example.com")

    flow_resp = client.post(
        "/api/v1/study-flow/capture-to-vocabulary",
        json={
            "user_id": user_id,
            "selected_text": "Apple",
            "source_url": "https://example.com/article",
            "source_sentence": "I eat an apple every day.",
        },
        headers=headers,
    )
    assert flow_resp.status_code == 200
    flow_data = flow_resp.json()
    assert flow_data["capture"]["selected_text"] == "Apple"
    assert flow_data["vocabulary"]["english_lemma"] == "apple"
    assert flow_data["created_new_vocabulary_item"] is True
    assert flow_data["queued_for_review"] is True

    # Second call should reuse existing vocabulary item by default.
    flow_resp_repeat = client.post(
        "/api/v1/study-flow/capture-to-vocabulary",
        json={
            "user_id": user_id,
            "selected_text": "apple",
            "source_sentence": "apple pie is tasty",
        },
        headers=headers,
    )
    assert flow_resp_repeat.status_code == 200
    repeat_data = flow_resp_repeat.json()
    assert repeat_data["created_new_vocabulary_item"] is False

    # Force mode should create a new vocabulary item.
    flow_resp_forced = client.post(
        "/api/v1/study-flow/capture-to-vocabulary",
        json={
            "user_id": user_id,
            "selected_text": "apple",
            "source_sentence": "forced duplicate",
            "force_new_vocabulary_item": True,
        },
        headers=headers,
    )
    assert flow_resp_forced.status_code == 200
    forced_data = flow_resp_forced.json()
    assert forced_data["created_new_vocabulary_item"] is True

    progress_resp = client.get(f"/api/v1/context/{user_id}/word-progress/apple", headers=headers)
    assert progress_resp.status_code == 200


def test_recommendations_rank_by_frequency_and_recency(client):
    user_id = create_user(client, "rank@example.com", "Rank User", "B1")
    headers = auth_headers(client, "rank@example.com")

    client.put(
        f"/api/v1/context/{user_id}",
        json={"cefr_level": "B1", "goals": ["practice"], "difficult_words": ["through"]},
        headers=headers,
    )

    client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: pear",
                    "expected_answer": "груша",
                    "user_answer": "яблоко",
                    "is_correct": False,
                },
                {
                    "exercise_id": 2,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "груша",
                    "is_correct": False,
                },
            ],
        },
        headers=headers,
    )
    client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 3,
                    "prompt": "Translate into Russian: pear",
                    "expected_answer": "груша",
                    "user_answer": "яблоко",
                    "is_correct": False,
                }
            ],
        },
        headers=headers,
    )

    rec_resp = client.get(f"/api/v1/context/{user_id}/recommendations?limit=3", headers=headers)
    assert rec_resp.status_code == 200
    data = rec_resp.json()

    assert data["words"][0] == "pear"
    assert "through" in data["words"]
    assert set(data["scores"].keys()) == set(data["words"])
    assert data["scores"]["pear"] > data["scores"]["through"]
    assert data["next_review_at"]["pear"] is not None


def test_srs_next_review_moves_forward_after_correct_answer(client):
    user_id = create_user(client, "srs@example.com", "Srs User", "A2")
    headers = auth_headers(client, "srs@example.com")

    client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "груша",
                    "is_correct": False,
                }
            ],
        },
        headers=headers,
    )
    rec_after_error = client.get(f"/api/v1/context/{user_id}/recommendations?limit=5", headers=headers).json()
    first_next_review = rec_after_error["next_review_at"]["apple"]
    assert first_next_review is not None

    client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 2,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "яблоко",
                    "is_correct": True,
                }
            ],
        },
        headers=headers,
    )
    rec_after_correct = client.get(f"/api/v1/context/{user_id}/recommendations?limit=5", headers=headers).json()
    second_next_review = rec_after_correct["next_review_at"]["apple"]
    assert second_next_review is not None
    assert second_next_review > first_next_review

    queue_after_correct = client.get(f"/api/v1/context/{user_id}/review-queue?limit=5", headers=headers)
    assert queue_after_correct.status_code == 200
    assert all(item["word"] != "apple" for item in queue_after_correct.json()["items"])


def test_review_queue_submit_updates_word_progress(client):
    user_id = create_user(client, "queue-submit@example.com", "Queue User", "B1")
    headers = auth_headers(client, "queue-submit@example.com")
    client.post(
        "/api/v1/vocabulary",
        json={
            "user_id": user_id,
            "english_lemma": "through",
            "russian_translation": "через",
        },
        headers=headers,
    )

    # First incorrect review creates due word and difficult-word signal.
    first_submit = client.post(
        f"/api/v1/context/{user_id}/review-queue/submit",
        json={"word": "through", "is_correct": False},
        headers=headers,
    )
    assert first_submit.status_code == 200
    first_data = first_submit.json()
    assert first_data["word"] == "through"
    assert first_data["russian_translation"] == "через"
    assert first_data["error_count"] >= 1
    assert first_data["correct_streak"] == 0

    context_resp = client.get(f"/api/v1/context/{user_id}", headers=headers)
    assert context_resp.status_code == 200
    assert "through" in context_resp.json()["difficult_words"]

    # Correct review should move next_review_at forward and remove it from due queue.
    second_submit = client.post(
        f"/api/v1/context/{user_id}/review-queue/submit",
        json={"word": "through", "is_correct": True},
        headers=headers,
    )
    assert second_submit.status_code == 200
    second_data = second_submit.json()
    assert second_data["correct_streak"] >= 1
    assert second_data["next_review_at"] > first_data["next_review_at"]

    queue_resp = client.get(f"/api/v1/context/{user_id}/review-queue?limit=10", headers=headers)
    assert queue_resp.status_code == 200
    assert all(item["word"] != "through" for item in queue_resp.json()["items"])

    progress_item_resp = client.get(f"/api/v1/context/{user_id}/word-progress/through", headers=headers)
    assert progress_item_resp.status_code == 200
    assert progress_item_resp.json()["word"] == "through"


def test_word_progress_list_and_item_with_translation(client):
    user_id = create_user(client, "progress-list@example.com", "Progress User", "A2")
    headers = auth_headers(client, "progress-list@example.com")

    client.post(
        "/api/v1/vocabulary",
        json={
            "user_id": user_id,
            "english_lemma": "apple",
            "russian_translation": "яблоко",
        },
        headers=headers,
    )

    client.post(
        f"/api/v1/context/{user_id}/review-queue/submit",
        json={"word": "apple", "is_correct": False},
        headers=headers,
    )

    list_resp = client.get(f"/api/v1/context/{user_id}/word-progress?limit=10&offset=0", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert len(list_data["items"]) >= 1
    assert list_data["items"][0]["word"] == "apple"
    assert list_data["items"][0]["russian_translation"] == "яблоко"

    item_resp = client.get(f"/api/v1/context/{user_id}/word-progress/apple", headers=headers)
    assert item_resp.status_code == 200
    item_data = item_resp.json()
    assert item_data["word"] == "apple"
    assert item_data["russian_translation"] == "яблоко"


def test_word_progress_filters_by_status_and_query(client):
    user_id = create_user(client, "progress-filter@example.com", "Filter User", "B1")
    headers = auth_headers(client, "progress-filter@example.com")

    # Troubled and due word.
    for _ in range(3):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "through", "is_correct": False},
            headers=headers,
        )

    # Mastered and upcoming word.
    for _ in range(3):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "apple", "is_correct": True},
            headers=headers,
        )

    due_resp = client.get(f"/api/v1/context/{user_id}/word-progress?status=due", headers=headers)
    assert due_resp.status_code == 200
    due_words = [item["word"] for item in due_resp.json()["items"]]
    assert "through" in due_words
    assert "apple" not in due_words

    upcoming_resp = client.get(f"/api/v1/context/{user_id}/word-progress?status=upcoming", headers=headers)
    assert upcoming_resp.status_code == 200
    upcoming_words = [item["word"] for item in upcoming_resp.json()["items"]]
    assert "apple" in upcoming_words

    mastered_resp = client.get(f"/api/v1/context/{user_id}/word-progress?status=mastered", headers=headers)
    assert mastered_resp.status_code == 200
    mastered_words = [item["word"] for item in mastered_resp.json()["items"]]
    assert "apple" in mastered_words

    troubled_resp = client.get(f"/api/v1/context/{user_id}/word-progress?status=troubled", headers=headers)
    assert troubled_resp.status_code == 200
    troubled_words = [item["word"] for item in troubled_resp.json()["items"]]
    assert "through" in troubled_words

    search_resp = client.get(f"/api/v1/context/{user_id}/word-progress?q=app", headers=headers)
    assert search_resp.status_code == 200
    search_words = [item["word"] for item in search_resp.json()["items"]]
    assert "apple" in search_words
    assert "through" not in search_words


def test_word_progress_supports_sorting(client):
    user_id = create_user(client, "progress-sort@example.com", "Sort User", "B1")
    headers = auth_headers(client, "progress-sort@example.com")

    for _ in range(2):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "pear", "is_correct": False},
            headers=headers,
        )
    for _ in range(4):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "apple", "is_correct": False},
            headers=headers,
        )

    sorted_resp = client.get(
        f"/api/v1/context/{user_id}/word-progress?sort_by=error_count&sort_order=desc",
        headers=headers,
    )
    assert sorted_resp.status_code == 200
    items = sorted_resp.json()["items"]
    assert len(items) >= 2
    assert items[0]["word"] == "apple"
    assert items[0]["error_count"] >= items[1]["error_count"]


def test_word_progress_threshold_filters(client):
    user_id = create_user(client, "thresholds@example.com", "Threshold User", "B1")
    headers = auth_headers(client, "thresholds@example.com")

    for _ in range(3):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "apple", "is_correct": True},
            headers=headers,
        )
    for _ in range(4):
        client.post(
            f"/api/v1/context/{user_id}/review-queue/submit",
            json={"word": "pear", "is_correct": False},
            headers=headers,
        )

    mastered_default = client.get(f"/api/v1/context/{user_id}/word-progress?status=mastered", headers=headers)
    assert mastered_default.status_code == 200
    mastered_words = [item["word"] for item in mastered_default.json()["items"]]
    assert "apple" in mastered_words

    mastered_strict = client.get(
        f"/api/v1/context/{user_id}/word-progress?status=mastered&min_streak=5",
        headers=headers,
    )
    assert mastered_strict.status_code == 200
    mastered_strict_words = [item["word"] for item in mastered_strict.json()["items"]]
    assert "apple" not in mastered_strict_words

    troubled_default = client.get(f"/api/v1/context/{user_id}/word-progress?status=troubled", headers=headers)
    assert troubled_default.status_code == 200
    troubled_words = [item["word"] for item in troubled_default.json()["items"]]
    assert "pear" in troubled_words

    troubled_strict = client.get(
        f"/api/v1/context/{user_id}/word-progress?status=troubled&min_errors=5",
        headers=headers,
    )
    assert troubled_strict.status_code == 200
    troubled_strict_words = [item["word"] for item in troubled_strict.json()["items"]]
    assert "pear" not in troubled_strict_words


def test_review_queue_bulk_submit_updates_multiple_words(client):
    user_id = create_user(client, "bulk-submit@example.com", "Bulk User", "B1")
    headers = auth_headers(client, "bulk-submit@example.com")
    client.post(
        "/api/v1/vocabulary",
        json={"user_id": user_id, "english_lemma": "through", "russian_translation": "через"},
        headers=headers,
    )
    client.post(
        "/api/v1/vocabulary",
        json={"user_id": user_id, "english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers,
    )

    bulk_resp = client.post(
        f"/api/v1/context/{user_id}/review-queue/submit-bulk",
        json={
            "items": [
                {"word": "through", "is_correct": False},
                {"word": "apple", "is_correct": True},
            ]
        },
        headers=headers,
    )
    assert bulk_resp.status_code == 200
    bulk_data = bulk_resp.json()
    assert bulk_data["user_id"] == user_id
    assert len(bulk_data["updated"]) == 2

    updated_map = {item["word"]: item for item in bulk_data["updated"]}
    assert updated_map["through"]["error_count"] >= 1
    assert updated_map["through"]["correct_streak"] == 0
    assert updated_map["through"]["russian_translation"] == "через"
    assert updated_map["apple"]["correct_streak"] >= 1
    assert updated_map["apple"]["russian_translation"] == "яблоко"

    context_resp = client.get(f"/api/v1/context/{user_id}", headers=headers)
    assert context_resp.status_code == 200
    assert "through" in context_resp.json()["difficult_words"]

    empty_bulk = client.post(
        f"/api/v1/context/{user_id}/review-queue/submit-bulk",
        json={"items": []},
        headers=headers,
    )
    assert empty_bulk.status_code == 200
    assert empty_bulk.json()["updated"] == []

    review_summary = client.get(f"/api/v1/analytics/review-summary?user_id={user_id}", headers=headers)
    assert review_summary.status_code == 200
    summary_data = review_summary.json()
    assert summary_data["user_id"] == user_id
    assert summary_data["total_tracked"] >= 2
    assert summary_data["due_now"] >= 1
    assert summary_data["mastered"] >= 0
    assert summary_data["troubled"] >= 0

    review_summary_strict = client.get(
        f"/api/v1/analytics/review-summary?user_id={user_id}&min_streak=5&min_errors=5",
        headers=headers,
    )
    assert review_summary_strict.status_code == 200
    strict_data = review_summary_strict.json()
    assert strict_data["mastered"] <= summary_data["mastered"]
    assert strict_data["troubled"] <= summary_data["troubled"]


def test_review_plan_returns_due_upcoming_and_recommendations(client):
    user_id = create_user(client, "plan@example.com", "Plan User", "B1")
    headers = auth_headers(client, "plan@example.com")

    client.post(
        "/api/v1/sessions/submit",
        json={
            "user_id": user_id,
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: pear",
                    "expected_answer": "груша",
                    "user_answer": "яблоко",
                    "is_correct": False,
                }
            ],
        },
        headers=headers,
    )
    client.post(
        f"/api/v1/context/{user_id}/review-queue/submit",
        json={"word": "apple", "is_correct": True},
        headers=headers,
    )

    plan_resp = client.get(f"/api/v1/context/{user_id}/review-plan?limit=10&horizon_hours=24", headers=headers)
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["user_id"] == user_id
    assert plan_data["due_count"] >= 1
    assert plan_data["upcoming_count"] >= 1
    assert isinstance(plan_data["due_now"], list)
    assert isinstance(plan_data["upcoming"], list)
    assert isinstance(plan_data["recommended_words"], list)
    assert any(item["word"] == "pear" for item in plan_data["due_now"])
    assert any(item["word"] == "apple" for item in plan_data["upcoming"])
    assert "pear" in plan_data["recommended_words"]


def test_delete_word_progress_removes_progress_and_difficult_word(client):
    user_id = create_user(client, "delete-progress@example.com", "Delete User", "A2")
    headers = auth_headers(client, "delete-progress@example.com")

    client.post(
        f"/api/v1/context/{user_id}/review-queue/submit",
        json={"word": "through", "is_correct": False},
        headers=headers,
    )

    delete_resp = client.delete(f"/api/v1/context/{user_id}/word-progress/through", headers=headers)
    assert delete_resp.status_code == 200
    delete_data = delete_resp.json()
    assert delete_data["progress_deleted"] is True
    assert delete_data["removed_from_difficult_words"] is True

    item_resp = client.get(f"/api/v1/context/{user_id}/word-progress/through", headers=headers)
    assert item_resp.status_code == 404

    context_resp = client.get(f"/api/v1/context/{user_id}", headers=headers)
    assert context_resp.status_code == 200
    assert "through" not in context_resp.json()["difficult_words"]

    second_delete = client.delete(f"/api/v1/context/{user_id}/word-progress/through", headers=headers)
    assert second_delete.status_code == 200
    second_data = second_delete.json()
    assert second_data["progress_deleted"] is False
    assert second_data["removed_from_difficult_words"] is False


def test_returns_403_for_user_id_mismatch_on_user_bound_endpoints(client):
    user_id = create_user(client, "mismatch@example.com", "Mismatch User", "A2")
    headers = auth_headers(client, "mismatch@example.com")

    vocab_resp = client.post(
        "/api/v1/vocabulary",
        json={"user_id": 999, "english_lemma": "cat", "russian_translation": "кот"},
        headers=headers,
    )
    assert vocab_resp.status_code == 403

    session_resp = client.post(
        "/api/v1/sessions/submit",
        json={"user_id": 999, "answers": []},
        headers=headers,
    )
    assert session_resp.status_code == 403

    context_resp = client.put(
        "/api/v1/context/999",
        json={"cefr_level": "A1", "goals": [], "difficult_words": []},
        headers=headers,
    )
    assert context_resp.status_code == 403

    translation_resp = client.post(
        "/api/v1/translate",
        json={"text": "hello", "user_id": 999},
        headers=headers,
    )
    assert translation_resp.status_code == 403

    exercise_resp = client.post(
        "/api/v1/exercises/generate",
        json={"user_id": 999, "size": 1, "vocabulary_ids": []},
        headers=headers,
    )
    assert exercise_resp.status_code == 403

    session_answers_resp = client.get(
        "/api/v1/sessions/999/answers?user_id=999",
        headers=headers,
    )
    assert session_answers_resp.status_code == 403

    recommendations_resp = client.get("/api/v1/context/999/recommendations", headers=headers)
    assert recommendations_resp.status_code == 403

    review_queue_resp = client.get("/api/v1/context/999/review-queue", headers=headers)
    assert review_queue_resp.status_code == 403

    review_submit_resp = client.post(
        "/api/v1/context/999/review-queue/submit",
        json={"word": "apple", "is_correct": True},
        headers=headers,
    )
    assert review_submit_resp.status_code == 403

    word_progress_list_resp = client.get("/api/v1/context/999/word-progress", headers=headers)
    assert word_progress_list_resp.status_code == 403

    word_progress_item_resp = client.get("/api/v1/context/999/word-progress/apple", headers=headers)
    assert word_progress_item_resp.status_code == 403

    review_bulk_resp = client.post(
        "/api/v1/context/999/review-queue/submit-bulk",
        json={"items": [{"word": "apple", "is_correct": True}]},
        headers=headers,
    )
    assert review_bulk_resp.status_code == 403

    review_summary_resp = client.get(
        "/api/v1/analytics/review-summary?user_id=999",
        headers=headers,
    )
    assert review_summary_resp.status_code == 403

    review_plan_resp = client.get("/api/v1/context/999/review-plan", headers=headers)
    assert review_plan_resp.status_code == 403

    delete_word_progress_resp = client.delete(
        "/api/v1/context/999/word-progress/apple",
        headers=headers,
    )
    assert delete_word_progress_resp.status_code == 403

    flow_resp = client.post(
        "/api/v1/study-flow/capture-to-vocabulary",
        json={"user_id": 999, "selected_text": "apple"},
        headers=headers,
    )
    assert flow_resp.status_code == 403

    auth_token_resp = client.post("/api/v1/auth/token", json={"email": "missing@example.com"})
    assert auth_token_resp.status_code == 404

def test_me_endpoints_work_for_review_and_analytics(client):
    create_user(client, "me-endpoints@example.com", "Me User", "B1")
    headers = auth_headers(client, "me-endpoints@example.com")

    create_vocab = client.post(
        "/api/v1/vocabulary",
        json={"english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers,
    )
    assert create_vocab.status_code == 200

    first_review = client.post(
        "/api/v1/context/me/review-queue/submit",
        json={"word": "apple", "is_correct": False},
        headers=headers,
    )
    assert first_review.status_code == 200

    queue_resp = client.get("/api/v1/context/me/review-queue?limit=10", headers=headers)
    assert queue_resp.status_code == 200
    assert queue_resp.json()["user_id"] >= 1

    plan_resp = client.get("/api/v1/context/me/review-plan?limit=10&horizon_hours=24", headers=headers)
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["user_id"] >= 1
    assert isinstance(plan_data["recommended_words"], list)

    summary_resp = client.get("/api/v1/analytics/review-summary/me", headers=headers)
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["total_tracked"] >= 1

    progress_resp = client.get("/api/v1/analytics/progress/me", headers=headers)
    assert progress_resp.status_code == 200
    progress_data = progress_resp.json()
    assert "avg_accuracy" in progress_data


def test_endpoints_accept_token_user_without_user_id_in_payload(client):
    create_user(client, "token-defaults@example.com", "Token Defaults", "A2")
    headers = auth_headers(client, "token-defaults@example.com")

    add_vocab = client.post(
        "/api/v1/vocabulary",
        json={"english_lemma": "through", "russian_translation": "через"},
        headers=headers,
    )
    assert add_vocab.status_code == 200

    translate_resp = client.post(
        "/api/v1/translate",
        json={"text": "through", "source_context": "walk through the park"},
        headers=headers,
    )
    assert translate_resp.status_code == 200

    exercises_resp = client.post(
        "/api/v1/exercises/generate",
        json={"size": 1, "vocabulary_ids": []},
        headers=headers,
    )
    assert exercises_resp.status_code == 200

    session_resp = client.post(
        "/api/v1/sessions/submit",
        json={
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: through",
                    "expected_answer": "через",
                    "user_answer": "через",
                    "is_correct": True,
                }
            ]
        },
        headers=headers,
    )
    assert session_resp.status_code == 200

    session_id = session_resp.json()["session"]["id"]
    answers_resp = client.get(f"/api/v1/sessions/{session_id}/answers", headers=headers)
    assert answers_resp.status_code == 200
    assert len(answers_resp.json()) == 1

    flow_resp = client.post(
        "/api/v1/study-flow/capture-to-vocabulary",
        json={"selected_text": "Apple", "source_sentence": "I eat an apple"},
        headers=headers,
    )
    assert flow_resp.status_code == 200


def test_vocabulary_me_endpoints_are_user_scoped(client):
    create_user(client, "vocab-me-1@example.com", "Vocab Me 1", "A2")
    headers_1 = auth_headers(client, "vocab-me-1@example.com")
    create_user(client, "vocab-me-2@example.com", "Vocab Me 2", "B1")
    headers_2 = auth_headers(client, "vocab-me-2@example.com")

    add_1 = client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers_1,
    )
    assert add_1.status_code == 200

    add_2 = client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "pear", "russian_translation": "груша"},
        headers=headers_2,
    )
    assert add_2.status_code == 200

    list_1 = client.get("/api/v1/vocabulary/me", headers=headers_1)
    assert list_1.status_code == 200
    words_1 = [item["english_lemma"] for item in list_1.json()]
    assert "apple" in words_1
    assert "pear" not in words_1

    list_2 = client.get("/api/v1/vocabulary/me", headers=headers_2)
    assert list_2.status_code == 200
    words_2 = [item["english_lemma"] for item in list_2.json()]
    assert "pear" in words_2
    assert "apple" not in words_2


def test_vocabulary_me_supports_update_and_delete(client):
    create_user(client, "vocab-crud-1@example.com", "Vocab Crud 1", "A2")
    headers_1 = auth_headers(client, "vocab-crud-1@example.com")
    create_user(client, "vocab-crud-2@example.com", "Vocab Crud 2", "B1")
    headers_2 = auth_headers(client, "vocab-crud-2@example.com")

    created = client.post(
        "/api/v1/vocabulary/me",
        json={
            "english_lemma": "Book",
            "russian_translation": "книга",
            "source_sentence": "I read a book.",
        },
        headers=headers_1,
    )
    assert created.status_code == 200
    item_id = created.json()["id"]
    assert created.json()["english_lemma"] == "book"
    assert created.json()["context_definition_ru"] is not None

    updated = client.put(
        f"/api/v1/vocabulary/me/{item_id}",
        json={
            "english_lemma": "book",
            "russian_translation": "книжка",
            "source_sentence": "This is my book.",
            "source_url": "https://example.com/book",
        },
        headers=headers_1,
    )
    assert updated.status_code == 200
    updated_data = updated.json()
    assert updated_data["english_lemma"] == "book"
    assert updated_data["russian_translation"] == "книжка"
    assert updated_data["source_url"] == "https://example.com/book"

    forbidden_update = client.put(
        f"/api/v1/vocabulary/me/{item_id}",
        json={"english_lemma": "book", "russian_translation": "книга"},
        headers=headers_2,
    )
    assert forbidden_update.status_code == 404

    delete_resp = client.delete(f"/api/v1/vocabulary/me/{item_id}", headers=headers_1)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True

    list_after_delete = client.get("/api/v1/vocabulary/me", headers=headers_1)
    assert list_after_delete.status_code == 200
    assert all(item["id"] != item_id for item in list_after_delete.json())


def test_capture_and_study_flow_me_endpoints_are_user_scoped(client):
    create_user(client, "capture-me-1@example.com", "Capture Me 1", "A2")
    headers_1 = auth_headers(client, "capture-me-1@example.com")
    create_user(client, "capture-me-2@example.com", "Capture Me 2", "B1")
    headers_2 = auth_headers(client, "capture-me-2@example.com")

    capture_1 = client.post(
        "/api/v1/capture/me",
        json={"selected_text": "apple", "source_sentence": "I eat an apple"},
        headers=headers_1,
    )
    assert capture_1.status_code == 200

    capture_2 = client.post(
        "/api/v1/capture/me",
        json={"selected_text": "pear", "source_sentence": "I eat a pear"},
        headers=headers_2,
    )
    assert capture_2.status_code == 200

    list_1 = client.get("/api/v1/capture/me", headers=headers_1)
    assert list_1.status_code == 200
    words_1 = [item["selected_text"] for item in list_1.json()]
    assert "apple" in words_1
    assert "pear" not in words_1

    list_2 = client.get("/api/v1/capture/me", headers=headers_2)
    assert list_2.status_code == 200
    words_2 = [item["selected_text"] for item in list_2.json()]
    assert "pear" in words_2
    assert "apple" not in words_2

    flow_1 = client.post(
        "/api/v1/study-flow/me/capture-to-vocabulary",
        json={"selected_text": "through", "source_sentence": "walk through the park"},
        headers=headers_1,
    )
    assert flow_1.status_code == 200
    assert flow_1.json()["vocabulary"]["english_lemma"] == "through"

    flow_2 = client.post(
        "/api/v1/study-flow/me/capture-to-vocabulary",
        json={"selected_text": "apple", "source_sentence": "I eat an apple"},
        headers=headers_2,
    )
    assert flow_2.status_code == 200
    assert flow_2.json()["vocabulary"]["english_lemma"] == "apple"


def test_me_endpoints_require_auth_token(client):
    no_auth_calls = [
        client.get("/api/v1/vocabulary/me"),
        client.post("/api/v1/vocabulary/me", json={"english_lemma": "apple", "russian_translation": "яблоко"}),
        client.get("/api/v1/capture/me"),
        client.post("/api/v1/capture/me", json={"selected_text": "apple"}),
        client.post("/api/v1/translate/me", json={"text": "apple"}),
        client.post("/api/v1/exercises/me/generate", json={"size": 1, "vocabulary_ids": []}),
        client.get("/api/v1/sessions/me"),
        client.get("/api/v1/sessions/me/1/answers"),
        client.get("/api/v1/context/me"),
        client.get("/api/v1/context/me/review-queue"),
        client.get("/api/v1/analytics/progress/me"),
        client.get("/api/v1/analytics/review-summary/me"),
        client.post("/api/v1/study-flow/me/capture-to-vocabulary", json={"selected_text": "apple"}),
    ]
    assert all(resp.status_code == 401 for resp in no_auth_calls)


def test_translate_and_exercises_me_endpoints_are_user_scoped(client):
    create_user(client, "me-ai-1@example.com", "Me AI 1", "A2")
    headers_1 = auth_headers(client, "me-ai-1@example.com")
    create_user(client, "me-ai-2@example.com", "Me AI 2", "B1")
    headers_2 = auth_headers(client, "me-ai-2@example.com")

    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "apple", "russian_translation": "яблоко"},
        headers=headers_1,
    )
    client.post(
        "/api/v1/vocabulary/me",
        json={"english_lemma": "pear", "russian_translation": "груша"},
        headers=headers_2,
    )

    translate_1 = client.post(
        "/api/v1/translate/me",
        json={"text": "apple", "source_context": "I eat an apple every day."},
        headers=headers_1,
    )
    assert translate_1.status_code == 200
    assert translate_1.json()["translated_text"] == "яблоко"

    exercises_1 = client.post(
        "/api/v1/exercises/me/generate",
        json={"size": 5, "vocabulary_ids": []},
        headers=headers_1,
    )
    assert exercises_1.status_code == 200
    data_1 = exercises_1.json()
    answers_1 = [item["answer"] for item in data_1["exercises"]]
    assert len(answers_1) == 5
    assert "яблоко" in answers_1
    assert "груша" not in answers_1

    exercises_2 = client.post(
        "/api/v1/exercises/me/generate",
        json={"size": 5, "vocabulary_ids": []},
        headers=headers_2,
    )
    assert exercises_2.status_code == 200
    data_2 = exercises_2.json()
    answers_2 = [item["answer"] for item in data_2["exercises"]]
    assert len(answers_2) == 5
    assert "груша" in answers_2
    assert "яблоко" not in answers_2


def test_sessions_me_endpoints_are_user_scoped(client):
    create_user(client, "sessions-me-1@example.com", "Sessions Me 1", "A2")
    headers_1 = auth_headers(client, "sessions-me-1@example.com")
    create_user(client, "sessions-me-2@example.com", "Sessions Me 2", "B1")
    headers_2 = auth_headers(client, "sessions-me-2@example.com")

    submit_1 = client.post(
        "/api/v1/sessions/submit",
        json={
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: apple",
                    "expected_answer": "яблоко",
                    "user_answer": "яблоко",
                    "is_correct": True,
                }
            ]
        },
        headers=headers_1,
    )
    assert submit_1.status_code == 200
    session_id_1 = submit_1.json()["session"]["id"]

    submit_2 = client.post(
        "/api/v1/sessions/submit",
        json={
            "answers": [
                {
                    "exercise_id": 1,
                    "prompt": "Translate into Russian: pear",
                    "expected_answer": "груша",
                    "user_answer": "груша",
                    "is_correct": True,
                }
            ]
        },
        headers=headers_2,
    )
    assert submit_2.status_code == 200
    session_id_2 = submit_2.json()["session"]["id"]

    sessions_1 = client.get("/api/v1/sessions/me", headers=headers_1)
    assert sessions_1.status_code == 200
    sessions_payload = sessions_1.json()
    ids_1 = [item["id"] for item in sessions_payload["items"]]
    assert session_id_1 in ids_1
    assert session_id_2 not in ids_1

    answers_1 = client.get(f"/api/v1/sessions/me/{session_id_1}/answers", headers=headers_1)
    assert answers_1.status_code == 200
    assert len(answers_1.json()) == 1

    answers_forbidden = client.get(f"/api/v1/sessions/me/{session_id_2}/answers", headers=headers_1)
    assert answers_forbidden.status_code == 404


def test_sessions_me_supports_filters_and_pagination(client):
    create_user(client, "sessions-filter@example.com", "Sessions Filter", "B1")
    headers = auth_headers(client, "sessions-filter@example.com")

    for is_correct in [True, False, True]:
        submit = client.post(
            "/api/v1/sessions/submit",
            json={
                "answers": [
                    {
                        "exercise_id": 1,
                        "prompt": "Translate into Russian: apple",
                        "expected_answer": "яблоко",
                        "user_answer": "яблоко" if is_correct else "груша",
                        "is_correct": is_correct,
                    }
                ]
            },
            headers=headers,
        )
        assert submit.status_code == 200

    page_1 = client.get("/api/v1/sessions/me?limit=2&offset=0", headers=headers)
    assert page_1.status_code == 200
    data_1 = page_1.json()
    assert data_1["total"] >= 3
    assert data_1["limit"] == 2
    assert data_1["offset"] == 0
    assert len(data_1["items"]) == 2

    page_2 = client.get("/api/v1/sessions/me?limit=2&offset=2", headers=headers)
    assert page_2.status_code == 200
    data_2 = page_2.json()
    assert data_2["total"] == data_1["total"]
    assert len(data_2["items"]) >= 1

    high_accuracy = client.get("/api/v1/sessions/me?min_accuracy=1", headers=headers)
    assert high_accuracy.status_code == 200
    assert all(item["accuracy"] >= 1 for item in high_accuracy.json()["items"])

    low_accuracy = client.get("/api/v1/sessions/me?max_accuracy=0", headers=headers)
    assert low_accuracy.status_code == 200
    assert all(item["accuracy"] <= 0 for item in low_accuracy.json()["items"])

    invalid_accuracy = client.get("/api/v1/sessions/me?min_accuracy=0.8&max_accuracy=0.2", headers=headers)
    assert invalid_accuracy.status_code == 400
