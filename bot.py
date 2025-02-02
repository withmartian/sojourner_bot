import logging
import sys
import dotenv

dotenv.load_dotenv()

import os
import json
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from fastapi import FastAPI, Request
import uvicorn
import requests
from sojourner import Sojourner, Result

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
fastapi_app = FastAPI()
handler = SlackRequestHandler(app)
sojourner_client = Sojourner()

logging.basicConfig(level=logging.INFO)


@app.event("message")
def handle_message(event, say):
    # This will handle all messages, including those in DMs
    if "files" in event:
        for file in event["files"]:
            handle_file_shared(file, say, event["channel"])


def handle_file_shared(file, say, channel):
    file_id = file["id"]
    filename = file["name"]

    result = say(
        text=f"Do you want to upload `{filename}` to Sojourner?",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Do you want to upload `{filename}` to Sojourner?",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Yes", "emoji": True},
                        "style": "primary",
                        "value": json.dumps(
                            {
                                "file_id": file_id,
                                "channel_id": channel,
                                "message_ts": "",
                            }
                        ),
                        "action_id": "upload_file_yes",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "No", "emoji": True},
                        "style": "danger",
                        "value": "no",
                        "action_id": "upload_file_no",
                    },
                ],
            },
        ],
    )

    # Update the value with the message timestamp
    value = json.loads(result["message"]["blocks"][1]["elements"][0]["value"])
    value["message_ts"] = result["ts"]
    result["message"]["blocks"][1]["elements"][0]["value"] = json.dumps(value)

    app.client.chat_update(
        channel=result["channel"],
        ts=result["ts"],
        blocks=result["message"]["blocks"],
        text="Do you want to upload this file to Sojourner?",
    )


@app.action("upload_file_yes")
def handle_yes(ack, body, client):
    ack()

    value = json.loads(body["actions"][0]["value"])
    file_id = value["file_id"]
    channel_id = value["channel_id"]
    message_ts = value["message_ts"]

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "client_name_modal",
            "title": {"type": "plain_text", "text": "Upload File to Sojourner"},
            "submit": {"type": "plain_text", "text": "Upload"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "client_name_block",
                    "element": {
                        "type": "static_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select client name",
                        },
                        "action_id": "client_name_select",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": client},
                                "value": client,
                            }
                            for client in sojourner_client.list_all_directories()
                        ],
                    },
                    "label": {"type": "plain_text", "text": "Client Name"},
                },
                {
                    "type": "input",
                    "block_id": "manifest_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "manifest_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter a description of the file",
                        },
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "File Description (Manifest)",
                    },
                },
            ],
            "private_metadata": json.dumps(
                {"file_id": file_id, "channel_id": channel_id, "message_ts": message_ts}
            ),
        },
    )


@app.action("upload_file_no")
def handle_no(ack, body, client):
    ack()
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    client.chat_delete(channel=channel_id, ts=message_ts)


@app.options("client_name_select")
def handle_client_options(ack, body):
    ack(options=get_client_options(body.get("value", "")))


@app.view("client_name_modal")
def handle_client_name_submission(ack, body, client, view):
    ack()

    selected_option = view["state"]["values"]["client_name_block"][
        "client_name_select"
    ]["selected_option"]
    client_name = (
        selected_option["value"]
        if selected_option
        else view["state"]["values"]["client_name_block"]["client_name_select"]["value"]
    )
    manifest = view["state"]["values"]["manifest_block"]["manifest_input"]["value"]

    metadata = json.loads(view["private_metadata"])
    file_id = metadata["file_id"]
    channel_id = metadata["channel_id"]
    message_ts = metadata["message_ts"]

    file_info = client.files_info(file=file_id)
    file_url = file_info["file"]["url_private_download"]
    response = requests.get(
        file_url, headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    )

    if response.status_code == 200:
        filename = file_info["file"]["name"]
        file_content = response.content
        result: Result = sojourner_client.store(
            client_name, filename, file_content, manifest=manifest
        )

        if result == Result.SUCCESS:
            client.chat_postMessage(
                channel=channel_id,
                text=f"File `{filename}` has been successfully uploaded to Sojourner for client `{client_name}`.\nManifest: `{manifest}`",
            )
        elif result == Result.BLOB_EXISTS:
            client.chat_postMessage(
                channel=channel_id,
                text=f"Failed to upload `{filename}` to Sojourner for `{client_name}`. A file with this name already exists.",
            )
        elif result == Result.UPLOAD_ERROR:
            client.chat_postMessage(
                channel=channel_id,
                text=f"Failed to upload `{filename}` to Sojourner for `{client_name}` due to an upload error. Please try again later.",
            )
        elif result == Result.METADATA_ERROR:
            client.chat_postMessage(
                channel=channel_id,
                text=f"Failed to upload `{filename}` to Sojourner for `{client_name}` due to a metadata error. Please check your manifest and try again.",
            )
        else:
            client.chat_postMessage(
                channel=channel_id,
                text=f"An unexpected error occurred while uploading `{filename}` to Sojourner for `{client_name}`.",
            )
        client.chat_delete(channel=channel_id, ts=message_ts)
    else:
        client.chat_postMessage(
            channel=channel_id, text="Sorry, I couldn't download the file."
        )


@fastapi_app.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@fastapi_app.get("/")
async def root():
    return {"message": "Slack bot is running"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(fastapi_app, host="0.0.0.0", port=port)
