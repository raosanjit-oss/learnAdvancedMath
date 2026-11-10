import os
from pathlib import Path
from dotenv import load_dotenv
# ai imports
from groq import Groq
from google import genai
from google.genai import types
from app_settings import get_setting
from lesson_tools import clean_manim_code, save_manim_code


project_directory = Path(__file__).resolve().parent
load_dotenv(project_directory / ".env")
topic_viability_model = "openai/gpt-oss-20b"
manim_coding_model = get_setting("MANIM_CODING_MODEL", "gemini-3.8-flash")


def ask_groq(topic, prompt_file):
    """Shared request used by the two small topic functions below."""
    api_key = get_setting("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Add GROQ_API_KEY to the project's .env file first.")
    with open(project_directory / prompt_file, encoding="utf-8") as file:
        instructions = file.read()
    with Groq(api_key=api_key, timeout=45, max_retries=0) as client:
        response = client.chat.completions.create(
            model=topic_viability_model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": topic},
            ],
        )
    return (response.choices[0].message.content or "").strip()


def check_topic(topic):
    # The UI asks the student for clarification; this function just returns a decision.
    if not topic.strip():
        raise ValueError("Please enter a topic first.")
    viability_result = ask_groq(topic, "topic_viability.txt")
    if viability_result not in ("Accepted", "Review", "Rejected"):
        raise ValueError("The topic checker gave an unexpected answer. Please try again.")
    return viability_result


def generate_topic_suggestions(topic):
    response_text = ask_groq(topic, "suggestions.txt")
    suggestions = []
    for line in response_text.splitlines():
        suggestion = line.strip().lstrip("0123456789.-)• ").strip()
        if suggestion and suggestion.casefold() not in [s.casefold() for s in suggestions]:
            suggestions.append(suggestion)
    if len(suggestions) != 3:
        raise ValueError("Could not get three distinct suggestions. Please try again.")
    return suggestions


def generate_manim_code(topic):
    api_key = get_setting("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Add GOOGLE_API_KEY to the project's .env file first.")
    with open(project_directory / "system_prompt.txt", encoding="utf-8") as file:
        prompt = file.read()
    with genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=180000)) as google_client:
        manim_code_output = google_client.models.generate_content(
            model=manim_coding_model,
            contents=topic,
            config=types.GenerateContentConfig(
                system_instruction=prompt,
                temperature=0.2,
                max_output_tokens=30000,
            ),
        )
    if not manim_code_output.candidates or not manim_code_output.candidates[0].content:
        raise ValueError("The model returned no lesson. Please try a more specific topic.")
    candidate = manim_code_output.candidates[0]
    if str(candidate.finish_reason).endswith("MAX_TOKENS"):
        raise ValueError("The lesson was cut short. Try a narrower topic.")
    manim_code = "".join(
        part.text or ""
        for part in candidate.content.parts or []
        if not part.thought
    )
    if not manim_code.strip():
        raise ValueError("The model returned an empty lesson. Please try again.")
    return manim_code


def save_lesson_code(lesson_code, topic="Math lesson"):
    # Validate and save in generated_lessons/<unique ID>/lesson.py.
    return save_manim_code(lesson_code, topic)


def clean_lesson_code(lesson_code):
    return clean_manim_code(lesson_code)

def main():
    topic = input("What topic do you want to learn about?\n")
    viability_result = check_topic(topic)
    if viability_result  == "Accepted":
        print("Topic accepted. Generating animation...")
        manim_code = clean_lesson_code(generate_manim_code(topic))
        print(save_lesson_code(manim_code, topic))
    elif viability_result == "Review":
        print("Try a more specific topic:")
        for suggestion in generate_topic_suggestions(topic):
            print(suggestion)
    elif viability_result == "Rejected":
        print("Topic rejected")
    else:
        print(f"Invalid response from viability checker: {viability_result}")
        print("Topic rejected.")
if __name__ == "__main__":
    main()

