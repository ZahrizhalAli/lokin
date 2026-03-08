

# 🎙️ Lokin: Real-Time AI Interviewer 

**Lokin** is an open-source Python framework for building real-time voice and multimodal conversational agents. Orchestrate audio and video, AI services, web transport, and conversation pipelines.

## Real-Time Pipeline

**Audio Capture**: Your browser captures microphone audio and sends it via WebRTC

**Share Screen** : Inject your screen sharing enabling Lokin to give you direct feedback.

**Voice Activity** Detection: [Silero VAD ](https://github.com/snakers4/silero-vad) detects when you start and stop speaking

**Speech Recognition**: Deepgram converts your speech to text in real-time

**Language Processing**: OpenAI’s GPT model generates an intelligent response

**Speech Synthesis**: Cartesia converts the response text back to natural speech

**Audio Playback**: The generated audio streams back to your browser

## 🔧 Getting Started

1. **Clone the Repository**

    ```bash
    git clone https://github.com/ZahrizhalAli/lokin.git
    cd lokin
    ```

2. **Instal uv**

    ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   > Refer to the [uv install documentation](https://docs.astral.sh/uv/getting-started/installation/).


3. Set up environment

   ```bash
   cp env.example .env
   ```


5. **Try the Sample App**

    Now you can test the local package with the sample app:

    ```bash
    uv sync  # Installs dependencies and the local package in editable mode
    uv run app.py
    ```

Then open http://localhost:7860 in your browser.


<img src="./ui/dist/assets/lokin.png" width="100%" style="position: absolute; top: 0; right: 0" alt="Project Logo"/>
