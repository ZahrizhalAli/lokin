import os

def load_prompt(filepath):
    """Reads a text/markdown file and returns its content as a string."""
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: Could not find the prompt file at {filepath}")
        return ""