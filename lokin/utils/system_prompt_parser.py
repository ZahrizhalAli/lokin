def load_prompt(filepath):
    """Read a prompt file and return its contents.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty or only whitespace. Running with an
            empty system prompt silently strips the bot's persona and rules,
            so we fail loudly instead.
    """
    with open(filepath, "r", encoding="utf-8") as file:
        content = file.read()

    if not content.strip():
        raise ValueError(f"Prompt file is empty: {filepath}")

    return content
