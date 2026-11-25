# Run Career Agent locally

Run these commands from the project root:

1. Activate the virtual environment:
   `source .venv/bin/activate`

2. Set the Python source path:
   `export PYTHONPATH="$PWD/src"`

3. Start the Telegram bot:
   `python -m career_agent bot run`

The Telegram bot token and allowed user ID must be configured
in the local `.env` file.

Never commit `.env` or private candidate profile data.
