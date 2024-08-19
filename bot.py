import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import dotenv

dotenv.load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

app = App(token=SLACK_BOT_TOKEN)


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
        with open(filename, "wb") as f:
            f.write(response.content)
        say(f"File '{filename}' has been downloaded and saved.")
    else:
        say("Sorry, I couldn't download the file.")


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
