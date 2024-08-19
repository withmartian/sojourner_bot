import os
import json
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import dotenv
from sojourner import Sojourner
from fuzzywuzzy import process

dotenv.load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)
sojourner_client = Sojourner()

# Load or initialize client names
CLIENT_NAMES_FILE = "client_names.json"
try:
    with open(CLIENT_NAMES_FILE, "r") as f:
        client_names = set(json.load(f))
except FileNotFoundError:
    client_names = set()


def save_client_names():
    with open(CLIENT_NAMES_FILE, "w") as f:
        json.dump(list(client_names), f, indent=2)


def get_client_options(input_value=""):
    matches = process.extract(input_value, client_names, limit=5)
    options = [
        {"text": {"type": "plain_text", "text": match}, "value": match}
        for match, score in matches
        if score > 60
    ]
    options.append(
        {
            "text": {"type": "plain_text", "text": "Add new client"},
            "value": "new_client",
        }
    )
    return options


@app.event("file_shared")
def handle_file_shared_events(body, say, client):
    file_id = body["event"]["file_id"]
    file_info = client.files_info(file=file_id)
    filename = file_info["file"]["name"]

    block_id = f"file_upload_{file_id}"

    result = client.chat_postMessage(
        channel=body["event"]["channel_id"],
        text=f"Do you want to upload '{filename}' to Sojourner?",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Do you want to upload '*{filename}*' to Sojourner?",
                },
            },
            {
                "type": "actions",
                "block_id": block_id,
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Yes", "emoji": True},
                        "style": "primary",
                        "value": json.dumps(
                            {
                                "file_id": file_id,
                                "channel_id": body["event"]["channel_id"],
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
        metadata={"event_payload": json.dumps(body)},
    )

    return result["ts"]


@app.action("upload_file_yes")
def handle_yes(ack, body, client):
    ack()

    value = json.loads(body["actions"][0]["value"])
    file_id = value["file_id"]
    channel_id = value["channel_id"]

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "client_name_modal",
            "title": {"type": "plain_text", "text": "Upload File to Sojourner"},
            "submit": {"type": "plain_text", "text": "Upload"},
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Select or add a client:*"},
                },
                {
                    "type": "input",
                    "block_id": "client_selection_block",
                    "element": {
                        "type": "external_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a client",
                        },
                        "action_id": "client_selection",
                        "min_query_length": 0,
                    },
                    "label": {"type": "plain_text", "text": "Client"},
                },
                {
                    "type": "input",
                    "block_id": "new_client_block",
                    "optional": True,
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "new_client_input",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter new client name",
                        },
                    },
                    "label": {"type": "plain_text", "text": "New Client Name"},
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
                {"file_id": file_id, "channel_id": channel_id}
            ),
        },
    )


@app.action("upload_file_no")
def handle_no(ack, body, client):
    ack()
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    client.chat_delete(channel=channel_id, ts=message_ts)


@app.options("client_selection")
def handle_client_options(ack, body):
    ack(options=get_client_options(body.get("value", "")))


@app.view("client_name_modal")
def handle_client_name_submission(ack, body, client, view):
    ack()

    selected_client = view["state"]["values"]["client_selection_block"][
        "client_selection"
    ]["selected_option"]
    new_client = view["state"]["values"]["new_client_block"]["new_client_input"][
        "value"
    ]
    manifest = view["state"]["values"]["manifest_block"]["manifest_input"]["value"]

    client_name = (
        new_client
        if selected_client["value"] == "new_client"
        else selected_client["value"]
    )

    metadata = json.loads(view["private_metadata"])
    file_id = metadata["file_id"]
    channel_id = metadata["channel_id"]

    if client_name:
        client_names.add(client_name)
        save_client_names()

    file_info = client.files_info(file=file_id)
    file_url = file_info["file"]["url_private_download"]
    response = requests.get(
        file_url, headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    )

    if response.status_code == 200:
        filename = file_info["file"]["name"]
        file_content = response.content
        success = sojourner_client.store(
            client_name, filename, file_content, manifest=manifest
        )

        if success:
            client.chat_postMessage(
                channel=channel_id,
                text=f"File '{filename}' has been uploaded to Sojourner for client '{client_name}'.\nManifest: {manifest}",
            )
        else:
            client.chat_postMessage(
                channel=channel_id, text=f"Failed to upload '{filename}' to Sojourner."
            )
    else:
        client.chat_postMessage(
            channel=channel_id, text="Sorry, I couldn't download the file."
        )


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
