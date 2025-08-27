import os
import sys
import json
import asyncio
import logging
import dotenv

from pathlib import Path

def check_api_key():
    """Check if Deepgram API key is available."""
    api_key = os.environ.get('DEEPGRAM_API_KEY')
    if not api_key:
        print("❌ ERROR: DEEPGRAM_API_KEY environment variable not found!")
        print("")
        print("Please set your Deepgram API key:")
        print("export DEEPGRAM_API_KEY=your_api_key_here")
        print("")
        print("Get your API key at: https://console.deepgram.com/signup?jump=keys")
        sys.exit(1)
    return api_key

# =============================================================================
# DJANGO CONFIGURATION & SETUP
# =============================================================================

dotenv.load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', '__main__')

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = 'django-live-transcription-starter-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'channels',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = '__main__'
ASGI_APPLICATION = '__main__.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # In-memory database for simplicity
    }
}

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'transcription': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =============================================================================
# DJANGO IMPORTS & INITIALIZATION
# =============================================================================

import django
from django.conf import settings
django.setup()

from django.http import HttpResponse
from django.urls import path, re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.generic.websocket import AsyncWebsocketConsumer
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions

logger = logging.getLogger('transcription')


# =============================================================================
# WEBSOCKET CONSUMER (BACKEND TRANSCRIPTION LOGIC)
# =============================================================================

class TranscriptionConsumer(AsyncWebsocketConsumer):
    """WebSocket Consumer for handling Deepgram live transcription."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deepgram_client = None
        self.deepgram_connection = None
        self.is_transcribing = False
        self.audio_buffer = bytearray()
        self.buffer_lock = asyncio.Lock()
        self.buffer_task = None
        self.detected_keywords = []
        self.patient_history = None
        self.load_patient_history()

    def load_patient_history(self):
        """Load the initial patient history from JSON file."""
        try:
            import json
            import os
            from pathlib import Path
            
            # Get the path to the static directory
            base_dir = Path(__file__).resolve().parent
            json_path = base_dir / 'static' / 'patient_history.json'
            
            with open(json_path, 'r', encoding='utf-8') as f:
                self.patient_history = json.load(f)
                logger.info("✅ Patient history loaded successfully")
        except Exception as e:
            logger.error(f"❌ Error loading patient history: {e}")
            self.patient_history = {}

    def merge_section_data(self, section_name, new_data):
        """Merge new data with existing section data instead of overwriting."""
        if not self.patient_history or section_name not in self.patient_history:
            return new_data
        
        existing_data = self.patient_history[section_name]
        merged_data = existing_data.copy()
        
        for key, new_value in new_data.items():
            if key in existing_data:
                existing_value = existing_data[key]
                
                # Handle list merging
                if isinstance(existing_value, list) and isinstance(new_value, list):
                    # Merge lists, avoiding duplicates
                    merged_list = existing_value.copy()
                    for item in new_value:
                        if item not in merged_list:
                            merged_list.append(item)
                    merged_data[key] = merged_list
                
                # Handle dictionary merging (for nested objects)
                elif isinstance(existing_value, dict) and isinstance(new_value, dict):
                    merged_data[key] = {**existing_value, **new_value}
                
                # Handle simple value replacement (for non-lists/dicts)
                else:
                    merged_data[key] = new_value
            else:
                # New key, just add it
                merged_data[key] = new_value
        
        # Update the in-memory patient history
        self.patient_history[section_name] = merged_data
        
        return merged_data

    async def connect(self):
        """Accept WebSocket connection and setup Deepgram client."""
        await self.accept()
        logger.info("Client connected")

        api_key = os.environ.get('DEEPGRAM_API_KEY')
        if not api_key:
            logger.error("DEEPGRAM_API_KEY not found in environment variables")
            await self.close(code=4000, reason="Missing API key")
            return

        # Validate API key format
        if not api_key.startswith('sha256'):
            logger.warning(f"API key format check: {api_key[:8]}... (expected format: sha256...)")
        else:
            logger.info(f"API key validated: {api_key[:8]}...")

        # Set up client configuration like the working Flask version
        config = DeepgramClientOptions(
            verbose=logging.WARN,
            options={"keepalive": "true"}
        )
        self.deepgram_client = DeepgramClient(api_key, config)
        logger.info("Deepgram client initialized with keepalive")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection and cleanup Deepgram connections."""
        logger.info(f"Client disconnected with code: {close_code}")

        if self.deepgram_connection:
            try:
                await self.deepgram_connection.finish()
                logger.info("Deepgram connection closed")
            except Exception as e:
                logger.error(f"Error closing Deepgram connection: {e}")

        # Clear audio buffer on disconnect
        async with self.buffer_lock:
            self.audio_buffer.clear()
            logger.info("Audio buffer cleared")

        self.is_transcribing = False

    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming WebSocket messages."""
        if text_data:
            try:
                data = json.loads(text_data)
                message_type = data.get('type')

                if message_type == 'toggle_transcription':
                    await self.handle_toggle_transcription()
                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except json.JSONDecodeError:
                logger.error("Invalid JSON received")

        elif bytes_data:
            print(f"📡 Received {len(bytes_data)} bytes")

            # Add audio data to buffer for decoupling
            async with self.buffer_lock:
                self.audio_buffer.extend(bytes_data)
                print(f"🧠 Buffer size: {len(self.audio_buffer)} bytes")

            # Send buffered audio if transcribing
            if self.is_transcribing and self.deepgram_connection:
                await self.process_audio_buffer()

    async def handle_toggle_transcription(self):
        """Toggle transcription on/off."""
        if self.is_transcribing:
            await self.stop_transcription()
        else:
            await self.start_transcription()

    async def start_transcription(self):
        """Start Deepgram live transcription."""
        try:
            logger.info("Starting Deepgram connection")
            await self.initialize_deepgram_connection()
            self.is_transcribing = True

            await self.send(text_data=json.dumps({
                'type': 'transcription_status',
                'status': 'started'
            }))

        except Exception as e:
            logger.error(f"Error starting transcription: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Failed to start transcription: {str(e)}"
            }))

    async def stop_transcription(self):
        """Stop Deepgram live transcription."""
        try:
            logger.info("Stopping transcription")

            if self.deepgram_connection:
                await self.deepgram_connection.finish()
                self.deepgram_connection = None

            # Clear audio buffer when stopping
            async with self.buffer_lock:
                self.audio_buffer.clear()
                logger.info("Audio buffer cleared on stop")

            self.is_transcribing = False

            await self.send(text_data=json.dumps({
                'type': 'transcription_status',
                'status': 'stopped'
            }))

        except Exception as e:
            logger.error(f"Error stopping transcription: {e}")



    async def process_audio_buffer(self):
        """Process buffered audio data and send to Deepgram."""
        try:
            buffer_data = None
            async with self.buffer_lock:
                if len(self.audio_buffer) > 0:
                    # Send buffer contents
                    buffer_data = bytes(self.audio_buffer)
                    self.audio_buffer.clear()  # Clear buffer after copying

            if buffer_data:
                await self.deepgram_connection.send(buffer_data)
                print(f"📤 Sent {len(buffer_data)} bytes to Deepgram")

        except Exception as e:
            print(f"❌ Error processing audio buffer: {e}")
            logger.error(f"Error processing audio buffer: {e}")

    def parse_transcription(self, transcript):
        """Parse transcription for keywords/phrases."""
        transcript_lower = transcript.lower()
        
        # Example: Detect specific words
        if "hello" in transcript_lower:
            print("🔍 Detected greeting!")
            return f"👋 {transcript}"
        
        # Example: Detect commands
        if "stop" in transcript_lower:
            print("🛑 Detected stop command!")
            return f"⏹️ {transcript}"
        
        # Example: Detect questions
        if transcript.strip().endswith("?"):
            return f"❓ {transcript}"
        
        return transcript

    def detect_keywords(self, transcript):
        """Return detected keywords from transcription."""
        keywords = []
        transcript_lower = transcript.lower()
        
        # Add your keyword detection logic here
        if "urgent" in transcript_lower:
            keywords.append("urgent")
        if "meeting" in transcript_lower:
            keywords.append("meeting")
        
        return keywords

    async def process_transcription_async(self, transcript):
        """Process transcription asynchronously without blocking the main flow."""
        try:
            # Your long-running parsing logic here
            parsed_result = await self.parse_transcription_with_api(transcript)
            self.detected_keywords = await self.detect_keywords_with_api(transcript)
            
            print("=" * 50)
            print("🔍 ASYNC PARSING COMPLETE:")
            print(f"📝 Original: '{transcript}'")
            print(f"🔍 Parsed: '{parsed_result}'")
            print("=" * 50)
            
            # Send parsed response if different from original
            if parsed_result != transcript:
                await self.send(text_data=json.dumps({
                    'type': 'parsed_response',
                    'transcription': parsed_result,
                    'original': transcript,
                    'detected_keywords': self.detected_keywords
                }))
            
            # NEW: Check for medical history updates
            section_updates = await self.detect_medical_history_updates(transcript)
            
            for section_name, new_data, completeness in section_updates:
                print(f"🏥 Updating section '{section_name}' with new data")
                
                # Merge new data with existing data instead of overwriting
                merged_data = self.merge_section_data(section_name, new_data)
                
                await self.send(text_data=json.dumps({
                    'type': 'section_update',
                    'section_name': section_name,
                    'new_data': merged_data,  # Send merged data for section display
                    'original_new_data': new_data,  # Send original new data for notification
                    'completeness': completeness,
                    'is_increment': True  # Flag indicating this is an increment value
                }))
                
        except Exception as e:
            print(f"❌ Error in async parsing: {e}")
            logger.error(f"Error in async parsing: {e}")

    async def parse_transcription_with_api(self, transcript):
        """Example of long-running parsing with API call."""
        transcript_lower = transcript.lower()
        
        # Simulate API call
        if "hello" in transcript_lower:
            # This could be a real API call that takes time
            await asyncio.sleep(5)  # Simulate API delay
            print("🔍 Detected greeting via API!")
            return f"👋 {transcript}"
        
        # More API calls...
        if "stop" in transcript_lower:
            await asyncio.sleep(0.5)  # Simulate API delay
            print("🛑 Detected stop command via API!")
            return f"⏹️ {transcript}"
        
        # Example: Detect questions
        if transcript.strip().endswith("?"):
            await asyncio.sleep(0.3)  # Simulate API delay
            print("❓ Detected question via API!")
            return f"❓ {transcript}"
        
        return transcript

    async def detect_keywords_with_api(self, transcript):
        """Example of long-running keyword detection with API call."""
        transcript_lower = transcript.lower()
        keywords = []

        if "urgent" in transcript_lower:
            await asyncio.sleep(0.3) # Simulate API delay
            keywords.append("urgent")
        if "meeting" in transcript_lower:
            await asyncio.sleep(0.4) # Simulate API delay
            keywords.append("meeting")

        return keywords

    async def detect_medical_history_updates(self, transcript):
        """Detect medical information in transcription and return section updates."""
        transcript_lower = transcript.lower()
        updates = []
        
        # Simulate API delay for medical entity detection
        await asyncio.sleep(0.2)
        
        # Example: Detect new symptoms
        if any(symptom in transcript_lower for symptom in ['headache', 'migraine', 'pain', 'dizziness', 'fatigue', 'nausea']):
            if 'headache' in transcript_lower or 'migraine' in transcript_lower:
                updates.append((
                    'illness_timeline',
                    {
                        'current_dominant_symptoms': ['headaches']  # Only the new symptom
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'dizziness' in transcript_lower:
                updates.append((
                    'dysautonomia_pots',
                    {
                        'orthostatic_intolerance': ['lightheadedness']  # Only the new symptom
                    },
                    0.05  # Increment completeness by 5%
                ))
        
        # Example: Detect new medications
        if any(med in transcript_lower for med in ['aspirin', 'ibuprofen', 'tylenol', 'acetaminophen', 'vitamin', 'supplement']):
            if 'aspirin' in transcript_lower:
                updates.append((
                    'medications_supplements',
                    {
                        'current_meds': [
                            {"name": "Aspirin", "dose": "81 mg", "route": "oral", "frequency": "as needed", "indication": "headache relief"}
                        ]
                    },
                    0.08  # Increment completeness by 8%
                ))
            elif 'vitamin d' in transcript_lower:
                updates.append((
                    'medications_supplements',
                    {
                        'current_supplements': ['vitamin D']  # Only the new supplement
                    },
                    0.05  # Increment completeness by 5%
                ))
        
        # Example: Detect family history updates
        if any(term in transcript_lower for term in ['mother', 'father', 'sister', 'brother', 'family', 'parent']):
            if 'diabetes' in transcript_lower and ('mother' in transcript_lower or 'father' in transcript_lower):
                updates.append((
                    'family_history',
                    {
                        'other_chronic': ["Mother: diabetes"]  # Only the new condition
                    },
                    0.06  # Increment completeness by 6%
                ))
            elif 'cancer' in transcript_lower:
                updates.append((
                    'family_history',
                    {
                        'other_chronic': ["Father: cancer"]  # Only the new condition
                    },
                    0.06  # Increment completeness by 6%
                ))
        
        # Example: Detect lab results
        if any(lab in transcript_lower for lab in ['blood test', 'lab result', 'esr', 'crp', 'ana', 'test result']):
            if 'esr' in transcript_lower and '15' in transcript:
                updates.append((
                    'immune_inflammatory',
                    {
                        'known_labs': {
                            'esr': 15  # Only the updated value
                        }
                    },
                    0.07  # Increment completeness by 7%
                ))
            elif 'crp' in transcript_lower and '2.5' in transcript:
                updates.append((
                    'immune_inflammatory',
                    {
                        'known_labs': {
                            'crp_mg_l': 2.5  # Only the updated value
                        }
                    },
                    0.07  # Increment completeness by 7%
                ))
        
        # Example: Detect lifestyle changes
        if any(term in transcript_lower for term in ['exercise', 'walking', 'steps', 'activity', 'workout']):
            if 'steps' in transcript_lower and any(str(num) in transcript for num in range(6000, 10000)):
                updates.append((
                    'lifestyle_function',
                    {
                        'exercise_tolerance': {
                            'avg_steps_per_day': 7500  # Only the updated value
                        }
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'exercise' in transcript_lower and 'improved' in transcript_lower:
                updates.append((
                    'lifestyle_function',
                    {
                        'exercise_tolerance': {
                            'intensity_tolerance': 'moderate',  # Only the updated value
                            'crash_frequency_per_month': 1  # Only the updated value
                        }
                    },
                    0.08  # Increment completeness by 8%
                ))
        
        # Example: Detect MCAS and allergy updates
        if any(term in transcript_lower for term in ['allergic', 'allergy', 'reaction', 'sensitive', 'intolerant', 'mcas', 'histamine', 'flushing', 'hives', 'rash', 'itching']):
            if 'peanuts' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'food_reactions': ['peanuts']  # Only the new food
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'shellfish' in transcript_lower or 'shrimp' in transcript_lower or 'crab' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'food_reactions': ['shellfish']  # Only the new food
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'tree nuts' in transcript_lower or 'almonds' in transcript_lower or 'walnuts' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'food_reactions': ['tree nuts']  # Only the new food
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'dairy' in transcript_lower or 'milk' in transcript_lower or 'cheese' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'food_reactions': ['dairy products']  # Only the new food
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'flushing' in transcript_lower or 'red face' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'skin_symptoms': ['facial flushing']  # Only the new symptom
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'hives' in transcript_lower or 'urticaria' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'skin_symptoms': ['hives']  # Only the new symptom
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'tinnitus' in transcript_lower or 'ringing ears' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'neuro_otologic': ['ear ringing']  # Only the new symptom
                    },
                    0.05  # Increment completeness by 5%
                ))
            elif 'seasonal' in transcript_lower and 'allergies' in transcript_lower:
                updates.append((
                    'mcas_allergic',
                    {
                        'seasonal_sensitivities': ['fall ragweed', 'summer grasses']  # Only the new sensitivities
                    },
                    0.06  # Increment completeness by 6%
                ))
            elif 'gluten' in transcript_lower:
                updates.append((
                    'gi_nutrition',
                    {
                        'food_intolerances_allergies': ['gluten']  # Only the new intolerance
                    },
                    0.05  # Increment completeness by 5%
                ))
        
        # Example: Detect new infections
        if any(term in transcript_lower for term in ['infection', 'cold', 'flu', 'virus', 'bacterial']):
            if 'covid' in transcript_lower:
                updates.append((
                    'infection_exposure_history',
                    {
                        'acute_infections_history': ['COVID-19 (2024)']  # Only the new infection
                    },
                    0.08  # Increment completeness by 8%
                ))
            elif 'strep' in transcript_lower:
                updates.append((
                    'infection_exposure_history',
                    {
                        'acute_infections_history': ['strep throat (2024)']  # Only the new infection
                    },
                    0.08  # Increment completeness by 8%
                ))
        
        # Example: Detect sleep changes
        if any(term in transcript_lower for term in ['sleep', 'insomnia', 'rest', 'tired', 'exhausted']):
            if 'sleep' in transcript_lower and 'improved' in transcript_lower:
                updates.append((
                    'energy_pem_me_cfs',
                    {
                        'sleep': ['improved sleep quality']  # Only the new sleep status
                    },
                    0.05  # Increment completeness by 5%
                ))
        
        return updates

    async def initialize_deepgram_connection(self):
        """Initialize Deepgram live transcription connection."""
        try:
            options = LiveOptions(
                model="nova-3",
                language="en-US",
                interim_results=True
            )

            # Create live transcription connection
            self.deepgram_connection = self.deepgram_client.listen.asyncwebsocket.v("1")

            # Capture Django consumer reference for callbacks
            consumer = self

            async def on_open(self, open, **kwargs):
                print("🟢 DEEPGRAM CONNECTION OPENED - Ready for audio!")
                print(f"🔍 Open event data: {open}")

            async def on_message(self, result, **kwargs):
                if result:
                    transcript = result.channel.alternatives[0].transcript
                    if transcript.strip():
                        print("=" * 50)
                        print("🎤 LIVE TRANSCRIPTION RECEIVED:")
                        print(f"📝 Original: '{transcript}'")
                        print(f"🔄 Final: {result.is_final}")
                        print("=" * 50)

                        # Always send transcription to frontend for real-time display
                        import asyncio
                        asyncio.create_task(consumer.send(text_data=json.dumps({
                            'type': 'transcription_update',
                            'transcription': transcript,
                            'is_final': result.is_final
                        })))
                        
                        # Only process final transcriptions for medical history updates
                        if result.is_final:
                            print("✅ Processing FINAL transcription for medical updates")
                            asyncio.create_task(consumer.process_transcription_async(transcript))
                        else:
                            print("⏳ Skipping interim transcription - waiting for final result")

            async def on_metadata(self, metadata, **kwargs):
                print(f"🆔 Metadata received")

            async def on_close(self, close, **kwargs):
                print(f"🔴 DEEPGRAM CONNECTION CLOSED: {close}")

            async def on_error(self, error, **kwargs):
                print(f"🔴 DEEPGRAM ERROR: {error}")

            async def on_unhandled(self, unhandled, **kwargs):
                print(f"🤷 UNHANDLED DEEPGRAM MESSAGE: {unhandled}")

            # Set up event handlers
            self.deepgram_connection.on(LiveTranscriptionEvents.Open, on_open)
            self.deepgram_connection.on(LiveTranscriptionEvents.Transcript, on_message)
            self.deepgram_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
            self.deepgram_connection.on(LiveTranscriptionEvents.Close, on_close)
            self.deepgram_connection.on(LiveTranscriptionEvents.Error, on_error)
            self.deepgram_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)

            # Start the connection with detailed logging
            logger.info(f"Attempting to start Deepgram connection with options: {options}")
            try:
                addons = {"no_delay": "true"}
                connection_result = await self.deepgram_connection.start(options, addons=addons)
                logger.info(f"Deepgram start() returned: {connection_result}")

                if not connection_result:
                    logger.error("Deepgram connection start returned False")
                    raise Exception("Failed to start Deepgram connection - start() returned False")

                logger.info("Deepgram connection initialized successfully")

            except Exception as start_error:
                logger.error(f"Exception during Deepgram start(): {start_error}")
                logger.error(f"Exception type: {type(start_error)}")
                raise Exception(f"Failed to start Deepgram connection: {start_error}")

        except Exception as e:
            logger.error(f"Failed to initialize Deepgram connection: {e}")
            raise


# =============================================================================
# DJANGO VIEWS & URL ROUTING
# =============================================================================

def index_view(request):
    """Serve the main transcription page from index.html file."""
    html_file_path = BASE_DIR / 'index.html'
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        return HttpResponse(html_content)
    except FileNotFoundError:
        return HttpResponse("""
        <h1>Error: index.html not found</h1>
        <p>Please ensure index.html is in the same directory as app.py</p>
        """, status=500)

urlpatterns = [
    path('', index_view, name='home'),
]

# Add static file serving for development
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

# Add static file URL patterns to serve CSS and other static files
urlpatterns += staticfiles_urlpatterns()
if DEBUG:
    urlpatterns += static(STATIC_URL, document_root=STATICFILES_DIRS[0])

# =============================================================================
# ASGI APPLICATION SETUP (WEBSOCKET ROUTING)
# =============================================================================

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter([
        re_path(r'ws/transcription/$', TranscriptionConsumer.as_asgi()),
    ]),
})

# =============================================================================
# MAIN EXECUTION & SERVER STARTUP
# =============================================================================
def main():
    """Main application entry point."""
    print("🎙️  Django Live Transcription Starter")
    print("=====================================")
    print("")

    api_key = check_api_key()
    print(f"✅ Deepgram API key loaded: {api_key[:8]}...")

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("🚀 Starting ASGI/Channel Layer")
    print("📡 WebSocket endpoint: ws://localhost:8080/ws/transcription/")
    print("🌐 Web interface: http://localhost:8080/")
    print("")
    print("Press Ctrl+C to stop the server")
    print("")

    try:
        from daphne.server import Server
        from daphne.endpoints import build_endpoint_description_strings

        server = Server(
            application=application,
            endpoints=build_endpoint_description_strings(host='0.0.0.0', port=8080),
            verbosity=1
        )
        server.run()
    except KeyboardInterrupt:
        print("")
        print("🛑 Server stopped")
        print("👋 Goodbye!")

if __name__ == '__main__':
    main()
