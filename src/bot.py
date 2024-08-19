import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import dotenv
from sojourner import Sojourner
import json

dotenv.load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)
sojourner_client = Sojourner()


@app.event("file_shared")
def handle_file_shared_events(body, say):
    print(body)
    file_id = body["event"]["file_id"]
    file_info = app.client.files_info(file=file_id)
    file_url = file_info["file"]["url_private_download"]

    # Download the file
    response = requests.get(
        file_url, headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    )
    if response.status_code == 200:
        filename = file_info["file"]["name"]
        file_content = response.content

        # Look up the channel name properly
        channel_id = body["event"]["channel_id"]
        channel_info = app.client.conversations_info(channel=channel_id)
        channel_name = channel_info["channel"]["name"]
        client = channel_name.split("-")[-1]

        success = sojourner_client.store(
            client,
            filename,
            file_content,
            manifest=f"File uploaded from Slack: {filename}",
        )

        if success:
            say(
                f"File '{filename}' has been downloaded and uploaded to the Sojourner bucket."
            )
        else:
            say(
                f"File '{filename}' was downloaded but couldn't be uploaded to the Sojourner bucket."
            )
    else:
        say("Sorry, I couldn't download the file.")


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
