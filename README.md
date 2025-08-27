# Django Live Transcription Starter

A Django-based real-time speech-to-text application using Deepgram API with medical history tracking capabilities.

## Features

- **Real-time Transcription**: Live speech-to-text using Deepgram's Nova-3 model
- **Medical History Tracking**: Dynamic updates to 12 medical history sections based on transcription content
- **WebSocket Communication**: Real-time updates between frontend and backend
- **Interactive UI**: Expandable medical history sections with completeness tracking
- **Visual Feedback**: Animated updates and progress indicators

## Medical History Sections

The application tracks 12 key medical history sections:

1. **Core Demographics** - Age, sex, ethnicity, occupation
2. **Illness Timeline** - Onset, progression, current symptoms
3. **Past Medical History** - Previous illnesses, hospitalizations
4. **Family History** - Autoimmune, allergies, chronic conditions
5. **Infection Exposure History** - Tick exposure, infections, travel
6. **GI & Nutrition** - Digestive issues, food intolerances
7. **Dysautonomia/POTS** - Orthostatic intolerance, blood pooling
8. **MCAS/Allergic** - Skin symptoms, food reactions
9. **Energy/PEM/ME-CFS** - Fatigue, sleep, cognitive issues
10. **Immune/Inflammatory** - Lab results, cytokines
11. **Medications/Supplements** - Current and past treatments
12. **Lifestyle/Function** - Exercise tolerance, work capacity

## Dynamic Section Updates

The application automatically detects medical information in transcription and updates relevant sections:

### Example Triggers:
- **Symptoms**: "I have headaches" → Updates `illness_timeline`
- **Medications**: "I take aspirin" → Updates `medications_supplements`
- **Family History**: "My mother has diabetes" → Updates `family_history`
- **Lab Results**: "ESR test came back at 15" → Updates `immune_inflammatory`
- **Lifestyle**: "I walk 8000 steps per day" → Updates `lifestyle_function`
- **Allergies**: "I'm allergic to peanuts" → Updates `mcas_allergic`

### Update Process:
1. **Detection**: Backend analyzes transcription for medical entities
2. **Mapping**: Identifies relevant medical history sections
3. **Update**: Sends WebSocket message with new data
4. **Display**: Frontend updates section content and completeness
5. **Visual Feedback**: Animations and progress bar updates

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set API Key**:
   ```bash
   export DEEPGRAM_API_KEY=your_api_key_here
   ```

3. **Run Application**:
   ```bash
   python app.py
   ```

4. **Access Interface**:
   - Web Interface: http://localhost:8080
   - WebSocket: ws://localhost:8080/ws/transcription/

## Testing

Run the test script to see section updates in action:

```bash
python test_section_updates.py
```

## WebSocket Message Types

- `transcription_update`: Raw transcription text
- `parsed_response`: Processed/parsed transcription
- `section_update`: Medical history section updates
- `transcription_status`: Connection status updates
- `error`: Error messages

## Architecture

- **Backend**: Django with Channels for WebSocket support
- **Frontend**: Vanilla JavaScript with WebSocket communication
- **Transcription**: Deepgram Live API with Nova-3 model
- **Medical Detection**: Custom entity recognition and mapping
- **UI**: Responsive design with expandable sections

## Customization

### Adding New Medical Entities

To add new medical entity detection, modify the `detect_medical_history_updates` method in `app.py`:

```python
# Example: Detect new condition
if 'condition_name' in transcript_lower:
    updates.append((
        'section_name',
        {
            'field_name': 'new_value'
        },
        0.95  # Updated completeness
    ))
```

### Modifying Section Structure

Update the `patient_history.json` file to modify section structure and initial data.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

