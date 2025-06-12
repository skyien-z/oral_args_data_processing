import json
import re

# --- Configuration: Phrases to identify for cleaning ---

# Phrases that manage the flow of conversation but aren't substantive.
# Will be removed if a turn consists solely of one of these.
TRAFFIC_PHRASES = {
    "i'm sorry.", "go ahead.", "no, please.", "thank you.", "yes.",
    "okay.", "all right.", "thank you, counsel.", "please."
}

# Short acknowledgements that can be removed if they are between two turns from the same speaker.
SIMPLE_INTERJECTIONS = {
    "yeah.", "right.", "mm-hmm.", "sure.", "no.", "correct.", "yes."
}


class TranscriptCleaner:
    """
    Cleans a Supreme Court oral argument transcript by removing conversational
    artifacts like interruptions, false starts, and non-substantive interjections.
    """

    def __init__(self, turns_data):
        self.turns = turns_data
        self.indices_to_delete = set()
        self.cleaned_turns = []

    def clean(self):
        """Orchestrates the cleaning process."""
        if not self.turns:
            return []

        self._flag_traffic_management_turns()
        self._flag_interrupted_false_starts()
        self._flag_simple_interjections()

        self._build_cleaned_list()
        self._merge_consecutive_turns()

        return self.cleaned_turns

    def _get_turn_text(self, turn):
        """Helper to get the full, normalized text from a turn's text_blocks."""
        return " ".join(block['text'] for block in turn.get('text_blocks', [])).strip().lower()

    def _flag_traffic_management_turns(self):
        """Pass 1: Flag turns that are just conversational traffic management."""
        for i, turn in enumerate(self.turns):
            text = self._get_turn_text(turn)
            # Remove laughter-only turns
            if text == "(laughter.)":
                self.indices_to_delete.add(i)
            # Remove phrases used to cede the floor or manage flow
            if text in TRAFFIC_PHRASES:
                self.indices_to_delete.add(i)

    def _flag_interrupted_false_starts(self):
        """Pass 2: Flag turns that are short, interrupted false starts."""
        for i, turn in enumerate(self.turns):
            if i in self.indices_to_delete:
                continue

            text = self._get_turn_text(turn)
            duration = turn['stop'] - turn['start']

            # A turn is a false start if it's short and ends with a dash.
            if duration < 3.0 and text.endswith('--'):
                # Find the next non-deleted turn to see who speaks next.
                next_speaker_index = -1
                for j in range(i + 1, len(self.turns)):
                    if j not in self.indices_to_delete:
                        next_speaker_index = j
                        break

                if next_speaker_index != -1:
                    # If the next speaker is different, this was a true interruption.
                    if self.turns[i]['speaker']['name'] != self.turns[next_speaker_index]['speaker']['name']:
                        self.indices_to_delete.add(i)

    def _flag_simple_interjections(self):
        """Pass 3: Flag simple interjections from a listener to a speaker who retains the floor."""
        for i, turn in enumerate(self.turns):
            if i in self.indices_to_delete:
                continue

            text = self._get_turn_text(turn)
            if text in SIMPLE_INTERJECTIONS:
                # Find the previous and next non-deleted turns
                prev_turn_index = -1
                for j in range(i - 1, -1, -1):
                    if j not in self.indices_to_delete:
                        prev_turn_index = j
                        break

                next_turn_index = -1
                for j in range(i + 1, len(self.turns)):
                    if j not in self.indices_to_delete:
                        next_turn_index = j
                        break

                # If the speaker before and after the interjection is the same, remove it.
                if (prev_turn_index != -1 and next_turn_index != -1 and
                        self.turns[prev_turn_index]['speaker']['name'] == self.turns[next_turn_index]['speaker']['name']):
                    self.indices_to_delete.add(i)

    def _build_cleaned_list(self):
        """Builds the initial list of turns, excluding the flagged ones."""
        self.cleaned_turns = [turn for i, turn in enumerate(self.turns) if i not in self.indices_to_delete]

    def _merge_consecutive_turns(self):
        """Pass 4: Merge adjacent turns from the same speaker."""
        if not self.cleaned_turns:
            return

        merged_turns = [self.cleaned_turns[0]]
        for i in range(1, len(self.cleaned_turns)):
            current_turn = self.cleaned_turns[i]
            last_merged_turn = merged_turns[-1]

            if current_turn['speaker']['name'] == last_merged_turn['speaker']['name']:
                # Merge: append text blocks and update stop time
                last_merged_turn['text_blocks'].extend(current_turn['text_blocks'])
                last_merged_turn['stop'] = current_turn['stop']
            else:
                # Different speaker, just append
                merged_turns.append(current_turn)

        self.cleaned_turns = merged_turns


def main(input_path, output_path):
    """
    Loads a transcript, cleans it, and saves the result.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Assuming the structure is consistent with the provided file
    original_turns = data['transcript']['sections'][0]['turns']

    cleaner = TranscriptCleaner(original_turns)
    cleaned_turns = cleaner.clean()

    data['transcript']['sections'][0]['turns'] = cleaned_turns

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Cleaned transcript saved to {output_path}")
    print(f"Original turn count: {len(original_turns)}")
    print(f"Cleaned turn count: {len(cleaned_turns)}")


if __name__ == '__main__':
    # Example usage:
    # python cleaner.py 2024.24-316-t01.json 2024.24-316-t01_cleaned.json
    import sys
    if len(sys.argv) != 3:
        print("Usage: python cleaner.py <input_json_path> <output_json_path>")
        sys.exit(1)
    
    main(sys.argv[1], sys.argv[2])