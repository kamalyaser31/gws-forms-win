import json
import subprocess
from unittest.mock import patch

import pytest

import form_builder as builder


def completed_process(stdout="{}", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def request_body(process_call):
    command = process_call.args[0]
    json_index = command.index("--json") + 1
    return json.loads(command[json_index])


def test_nonzero_gws_exit_raises_typed_error():
    failed_process = completed_process(stderr="permission denied", returncode=7)
    with patch("form_builder.subprocess.run", return_value=failed_process):
        with pytest.raises(builder.GwsCommandError) as error:
            builder.run_gws(["forms", "forms", "get"], verbose=False)

    assert error.value.returncode == 7
    assert "permission denied" in str(error.value)


def test_batch_update_binds_request_to_revision():
    with patch(
        "form_builder.subprocess.run", return_value=completed_process()
    ) as gws_process:
        builder.batch_update(
            "FORM_ID",
            [{"deleteItem": {"location": {"index": 1}}}],
            revision_id="revision-7",
        )

    body = request_body(gws_process.call_args)
    assert body["writeControl"] == {"requiredRevisionId": "revision-7"}


def test_empty_form_does_not_send_empty_batch_update():
    created_form = json.dumps(
        {
            "formId": "FORM_ID",
            "responderUri": "https://example.test/respond",
            "revisionId": "revision-1",
        }
    )
    with patch(
        "form_builder.subprocess.run",
        return_value=completed_process(stdout=created_form),
    ) as gws_process:
        form = builder.build_form("Empty form", [])

    assert form["formId"] == "FORM_ID"
    assert gws_process.call_count == 1
