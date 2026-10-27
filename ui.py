import os
import sys
import shutil
import tempfile
from pathlib import Path
from func import clone_audio
from PySide6.QtCore import Qt, QUrl, QThread, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSlider, QVBoxLayout, QWidget
)
from PySide6.QtMultimedia import (
    QAudioOutput, QMediaPlayer, QMediaCaptureSession,
    QAudioInput, QMediaRecorder, QMediaFormat
)

APP_STYLE = """
QMainWindow, QWidget#centralWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #eaf2ff, stop:0.42 #f5f7fb, stop:1 #f5f7fb);
    color: #172033;
    font-family: Inter, "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}
QScrollArea { border: none; background: transparent; }
QWidget#page { background: transparent; }
QFrame.card {
    background: rgba(255,255,255,0.98);
    border: 1px solid #e4eaf4;
    border-radius: 20px;
}
QLabel#cardTitle {
    color: #172033;
    font-size: 28px;
    font-weight: 750;
    padding-bottom: 2px;
}
QLabel.fieldLabel {
    color: #35435a;
    font-size: 13px;
    font-weight: 700;
}
QLabel.bodyText {
    color: #35435a;
    font-size: 13px;
}
QLabel.muted {
    color: #8490a3;
    font-size: 12px;
}
QLabel.fileName {
    color: #64748b;
    font-size: 12px;
}
QLineEdit {
    min-height: 43px;
    padding: 10px 12px;
    color: #172033;
    background: #ffffff;
    border: 1px solid #dce4f0;
    border-radius: 10px;
    selection-background-color: #3976e8;
}
QLineEdit:focus { border: 1px solid #5287ee; }
QLineEdit::placeholder { color: #8a97aa; }
QPushButton {
    min-height: 40px;
    padding: 9px 17px;
    border: 1px solid transparent;
    border-radius: 10px;
    background: #356fe0;
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
}
QPushButton:hover { background: #2559c5; }
QPushButton:pressed { background: #194da9; }
QPushButton:disabled { background: #aabde0; color: #f8faff; }
QPushButton#secondary {
    color: #245dc4;
    background: #edf4ff;
    border: 1px solid #d8e4f8;
}
QPushButton#secondary:hover { background: #dceaff; }
QPushButton#stop { background: #dc4e5a; }
QPushButton#stop:hover { background: #bd3542; }
QPushButton#green { background: #17865b; }
QFrame.dropZone {
    background: #f8faff;
    border: 2px dashed #b6c9e8;
    border-radius: 15px;
}
QFrame.dropZone[dragging="true"] {
    border-color: #5287ee;
    background: #f0f5ff;
}
QFrame.softPanel {
    background: #fbfcff;
    border: 1px solid #e5eaf3;
    border-radius: 12px;
}
QFrame.wavePanel {
    background: #f8faff;
    border: 1px solid #e0e8f5;
    border-radius: 10px;
}
QSlider::groove:horizontal {
    height: 6px; background: #dce5f3; border-radius: 3px;
}
QSlider::sub-page:horizontal { background: #3976e8; border-radius: 3px; }
QSlider::add-page:horizontal { background: #dce5f3; border-radius: 3px; }
QSlider::handle:horizontal {
    width: 15px; margin: -6px 0; border-radius: 8px;
    background: #3976e8; border: 3px solid white;
}
"""


class DropZone(QFrame):
    """Drop audio files here or use Choose File."""

    def __init__(self, on_file_selected):
        super().__init__()

        self.setObjectName("dropZone")
        self.setProperty("class", "dropZone")
        self.setAcceptDrops(True)
        self.on_file_selected = on_file_selected
        self.setMinimumHeight(155)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.prompt = QLabel("Drag and drop your file here")
        self.prompt.setObjectName("bodyText")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.choose_button = QPushButton("Choose File")
        self.choose_button.clicked.connect(self.choose_file)

        self.selected_name = QLabel("")
        self.selected_name.setObjectName("muted")
        self.selected_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_name.setWordWrap(True)

        layout.addWidget(self.prompt)
        layout.addWidget(
            self.choose_button,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addWidget(self.selected_name)

    def choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an audio file",
            str(Path.home()),
            (
                "Audio files (*.mp3 *.wav *.ogg *.oga *.m4a "
                "*.aac *.flac *.webm *.opus);;All files (*)"
            ),
        )

        if file_path:
            self.on_file_selected(file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            if any(url.isLocalFile() for url in urls):
                self.setProperty("dragging", True)
                self.style().unpolish(self)
                self.style().polish(self)
                event.acceptProposedAction()
                return

        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragging", False)
        self.style().unpolish(self)
        self.style().polish(self)

        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.on_file_selected(url.toLocalFile())
                event.acceptProposedAction()
                return

        event.ignore()


class CloneWorker(QThread):
    """Run voice generation in a background thread."""

    finished_successfully = Signal(str)
    failed = Signal(str)

    def __init__(self, ref_audio, ref_text, speech_to_generate):
        super().__init__()

        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.speech_to_generate = speech_to_generate

    def run(self):
        try:
            from func import clone_audio

            output_path = clone_audio(
                ref_audio=self.ref_audio,
                ref_text=self.ref_text,
                speech_to_generate=self.speech_to_generate,
            )

            if not output_path:
                raise RuntimeError(
                    "The generation function did not return an output path."
                )

            output_path = os.path.abspath(output_path)

            if not os.path.isfile(output_path):
                raise FileNotFoundError(
                    f"The generated audio file was not found:\n{output_path}"
                )

            self.finished_successfully.emit(output_path)

        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


class AudioCard(QFrame):
    def __init__(self, title, kind="reference"):
        super().__init__()

        self.setObjectName("card")
        self.setProperty("class", "card")

        self.kind = kind
        self.selected_file_path = ""
        self.generated_file_path = ""

        self.audio_output = QAudioOutput(self)
        self.audio_player = QMediaPlayer(self)
        self.audio_player.setAudioOutput(self.audio_output)

        self.audio_player.errorOccurred.connect(
            self.handle_playback_error
        )
        self.audio_player.playbackStateChanged.connect(
            self.update_play_button
        )

        # Setup audio recording session
        self.capture_session = QMediaCaptureSession(self)
        self.audio_input = QAudioInput(self)
        self.capture_session.setAudioInput(self.audio_input)
        
        self.recorder = QMediaRecorder(self)
        
        # Enforce valid WAV file encoding
        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        
        self.recorder.setMediaFormat(media_format)
        self.recorder.setAudioSampleRate(44100)
        self.recorder.setAudioChannelCount(1)
        self.recorder.setQuality(QMediaRecorder.Quality.HighQuality)
        
        self.capture_session.setRecorder(self.recorder)
        
        # Set a temporary file path for the active recording
        self.temp_record_path = os.path.join(tempfile.gettempdir(), f"temp_record_{id(self)}.wav")
        self.recorder.setOutputLocation(QUrl.fromLocalFile(self.temp_record_path))

        # Setup recording animation components
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.animate_recording)
        self.wave_pattern = [
            "▂", "▄", "▆", "▃", "▅", "▂", "▇", "▄", "▂", "▅", 
            "▃", "▆", "▂", "▄", "▅", "▃", "▇", "▂", "▅", "▄", "▃", "▆"
        ]

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        self.clone_worker = None
        self.loading_frame_index = 0
        self.loading_frames = ["◐", "◓", "◑", "◒"]

        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self.animate_loading)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 28, 30, 30)
        outer.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(8)

        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addWidget(heading, 1)

        self.loading_label = QLabel("")
        self.loading_label.setStyleSheet(
            "color: #3976e8; font-size: 13px; font-weight: 700;"
        )
        self.loading_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.loading_label.setMinimumWidth(110)
        self.loading_label.hide()

        header.addWidget(self.loading_label)
        outer.addLayout(header)

        if kind == "reference":
            self.build_voice_cloner(outer)
        else:
            self.build_voice_manipulator(outer)

    def build_voice_cloner(self, outer):
        outer.addWidget(self.field_label("Add a voice reference"))

        self.drop_zone = DropZone(self.set_selected_file)
        outer.addWidget(self.drop_zone)

        outer.addWidget(self.field_label("Record instead"))
        outer.addLayout(self.record_row())

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.exact_text = QLineEdit()
        self.exact_text.setPlaceholderText(
            "Exact speech (text) said on the audio given"
        )
        outer.addWidget(self.exact_text)

        outer.addWidget(self.selected_row("Selected file:"))

        self.speech_to_generate = QLineEdit()
        self.speech_to_generate.setPlaceholderText("Speech to generate")

        clone_row = QHBoxLayout()
        clone_row.setSpacing(10)
        clone_row.addWidget(self.speech_to_generate, 1)

        self.clone_button = QPushButton("Clone")
        self.clone_button.setEnabled(False)
        self.clone_button.clicked.connect(self.start_clone)

        clone_row.addWidget(self.clone_button)
        outer.addLayout(clone_row)

        outer.addWidget(
            self.selected_row("Generated clone:", generated=True)
        )

        self.exact_text.textChanged.connect(self.validate_clone_fields)
        self.speech_to_generate.textChanged.connect(
            self.validate_clone_fields
        )

    def build_voice_manipulator(self, outer):
        outer.addWidget(self.field_label("Pick an audio file"))

        self.drop_zone = DropZone(self.set_selected_file)
        outer.addWidget(self.drop_zone)

        outer.addWidget(self.field_label("Record instead"))
        outer.addLayout(self.record_row())

        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        outer.addWidget(self.selected_row("Selected file:"))

        outer.addWidget(
            self.subsection(
                "Noise Filtered",
                "Processed audio output",
                "Filtered audio:",
                "Not generated",
                "Filter",
            )
        )

        outer.addWidget(self.pitch_volume_section())

    def field_label(self, text):
        label = QLabel(text)
        label.setProperty("class", "fieldLabel")
        label.setObjectName("fieldLabel")
        return label

    def record_row(self):
        row = QHBoxLayout()
        row.setSpacing(9)

        self.record_btn = QPushButton("●  Record")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.setEnabled(False)

        self.record_btn.clicked.connect(self.start_recording)
        self.stop_btn.clicked.connect(self.stop_recording)

        row.addWidget(self.record_btn)
        row.addWidget(self.stop_btn)

        wave = QFrame()
        wave.setObjectName("wavePanel")

        wave_layout = QHBoxLayout(wave)
        wave_layout.setContentsMargins(8, 4, 8, 4)

        # Setup animated soundwave label
        self.wave_bars = QLabel(" ".join(self.wave_pattern))
        self.wave_bars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wave_bars.setStyleSheet(
            "color:#cbd5e1; font-size:14px;" # Light gray (idle state)
        )

        wave_layout.addWidget(self.wave_bars)
        row.addWidget(wave, 1)

        return row
    
    def animate_recording(self):
        # Shift the character array by 1 to create an animation
        self.wave_pattern = self.wave_pattern[1:] + [self.wave_pattern[0]]
        self.wave_bars.setText(" ".join(self.wave_pattern))

    def start_recording(self):
        self.status.setText("Recording audio...")
        self.record_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        # Start soundwave animation (red)
        self.wave_bars.setStyleSheet("color:#dc4e5a; font-size:14px;") 
        self.record_timer.start(100) # update every 100ms
        
        self.recorder.record()

    def stop_recording(self):
        self.recorder.stop()
        self.status.setText("Recording stopped. Choose where to save...")
        self.record_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # Stop soundwave animation (grey out)
        self.record_timer.stop()
        self.wave_bars.setStyleSheet("color:#cbd5e1; font-size:14px;") 

        # Ask the user where to save the file
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Recorded Audio",
            str(Path.home() / "recorded_voice.wav"),
            "Audio Files (*.wav);;All files (*)"
        )

        if save_path:
            try:
                # Copy from the temporary location to the chosen destination
                shutil.copy(self.temp_record_path, save_path)
                self.status.setText(f"Recording saved to: {Path(save_path).name}")
                
                # Automatically select the new recording in the UI
                self.set_selected_file(save_path) 
            except Exception as e:
                QMessageBox.critical(
                    self, 
                    "Save Failed", 
                    f"Failed to save recording:\n{e}"
                )
        else:
            self.status.setText("Recording discarded.")

    def selected_row(self, label_text, generated=False):
        panel = QFrame()
        panel.setObjectName("softPanel")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(4)

        default_text = "No file generated" if generated else "No file selected"
        
        file_label = self.field_label(f"{label_text} {default_text}")
        file_label.setStyleSheet(
            "font-size:12px; color:#64748b; font-weight:600;"
        )
        file_label.setWordWrap(True)
        file_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        file_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        file_label.setMinimumWidth(0)

        if generated:
            self.generated_file_label = file_label
        else:
            self.selected_file_label = file_label

        info.addWidget(file_label)
        layout.addLayout(info, 1)

        play = QPushButton("Play")
        play.setObjectName("secondary")
        play.setMinimumWidth(76)
        play.setEnabled(False)

        if generated:
            self.generated_play_button = play
            play.clicked.connect(
                lambda: self.toggle_playback(
                    self.generated_file_path,
                    self.generated_play_button,
                )
            )
        else:
            self.play_button = play
            play.clicked.connect(
                lambda: self.toggle_playback(
                    self.selected_file_path,
                    self.play_button,
                )
            )

        layout.addWidget(play)

        return panel

    def subsection(self, title, subtitle, label, filename, action):
        section = QFrame()
        section.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid #e9edf5; }"
        )

        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(12)

        heading = QVBoxLayout()

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "font-size:16px; font-weight:750; color:#1e293b;"
        )

        sub_label = QLabel(subtitle)
        sub_label.setObjectName("muted")

        heading.addWidget(title_label)
        heading.addWidget(sub_label)
        layout.addLayout(heading)

        panel = QFrame()
        panel.setObjectName("softPanel")

        row = QHBoxLayout(panel)
        row.setContentsMargins(13, 10, 13, 10)

        row.addWidget(QLabel(label))

        file = QLabel(filename)
        file.setObjectName("muted")
        row.addWidget(file, 1)

        play = QPushButton("Play")
        play.setObjectName("secondary")
        play.setEnabled(False)
        row.addWidget(play)

        layout.addWidget(panel)

        button = QPushButton(action)
        button.setEnabled(False)
        layout.addWidget(button)

        return section

    def pitch_volume_section(self):
        section = QFrame()
        section.setStyleSheet(
            "QFrame { border: none; border-top: 1px solid #e9edf5; }"
        )

        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Pitch and Volume Alter")
        title.setStyleSheet(
            "font-size:16px; font-weight:750; color:#1e293b;"
        )

        subtitle = QLabel("Adjust the audio before generating the output")
        subtitle.setObjectName("muted")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.output_row())

        controls = QFrame()
        controls.setObjectName("softPanel")

        grid = QVBoxLayout(controls)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setSpacing(17)

        self.pitch_value = QLabel("1.00×")
        grid.addLayout(
            self.slider_control(
                "Pitch", "Lower", "Normal", "Higher",
                50, 200, 100, self.pitch_value
            )
        )

        self.volume_value = QLabel("+100%")
        grid.addLayout(
            self.slider_control(
                "Volume Boost", "Original", "+100%", "+200%",
                0, 200, 100, self.volume_value
            )
        )

        generate = QPushButton("Generate")
        generate.setEnabled(False)
        grid.addWidget(generate)

        layout.addWidget(controls)

        return section

    def slider_control(
        self, title, left, middle, right,
        minimum, maximum, value, value_label
    ):
        wrapper = QVBoxLayout()

        heading = QHBoxLayout()

        name = QLabel(title)
        name.setStyleSheet(
            "font-size:12px; font-weight:750; color:#35435a;"
        )

        value_label.setStyleSheet(
            "font-size:12px; font-weight:750; color:#2f68d4;"
        )

        heading.addWidget(name)
        heading.addStretch()
        heading.addWidget(value_label)
        wrapper.addLayout(heading)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)

        if title == "Pitch":
            slider.valueChanged.connect(
                lambda v: value_label.setText(f"{v / 100:.2f}×")
            )
        else:
            slider.valueChanged.connect(
                lambda v: value_label.setText(f"+{v}%")
            )

        wrapper.addWidget(slider)

        labels = QHBoxLayout()

        for text in (left, middle, right):
            item = QLabel(text)
            item.setObjectName("muted")
            labels.addWidget(item)

        wrapper.addLayout(labels)

        return wrapper

    def output_row(self):
        panel = QFrame()
        panel.setObjectName("softPanel")

        row = QHBoxLayout(panel)
        row.setContentsMargins(13, 10, 13, 10)

        row.addWidget(QLabel("Altered audio:"))

        label = QLabel("No output generated")
        label.setObjectName("muted")
        row.addWidget(label, 1)

        play = QPushButton("Play")
        play.setObjectName("secondary")
        play.setEnabled(False)
        row.addWidget(play)

        return panel

    def set_selected_file(self, file_path):
        path = os.path.abspath(os.path.expanduser(file_path))

        if not os.path.isfile(path):
            QMessageBox.warning(
                self,
                "Invalid file",
                "Please choose a valid local file.",
            )
            return

        suffix = Path(path).suffix.lower()

        valid = {
            ".mp3", ".wav", ".ogg", ".oga", ".m4a",
            ".aac", ".flac", ".webm", ".opus",
        }

        if suffix not in valid:
            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please choose a supported audio file.",
            )
            return

        self.audio_player.stop()
        self.selected_file_path = path

        filename = Path(path).name

        self.drop_zone.selected_name.setText(filename)
        self.selected_file_label.setText(
            f"Selected file: {filename}\n{path}"
        )
        self.selected_file_label.setToolTip(path)

        self.play_button.setEnabled(True)
        self.play_button.setText("Play")

        self.status.setText("Selected file path saved.")
        self.status.setToolTip(path)

        if self.kind == "reference":
            self.validate_clone_fields()

    def validate_clone_fields(self):
        if self.kind != "reference":
            return

        all_fields_filled = (
            bool(self.selected_file_path)
            and os.path.isfile(self.selected_file_path)
            and bool(self.exact_text.text().strip())
            and bool(self.speech_to_generate.text().strip())
        )

        is_running = (
            self.clone_worker is not None
            and self.clone_worker.isRunning()
        )

        self.clone_button.setEnabled(
            all_fields_filled and not is_running
        )

    def start_clone(self):
        if self.kind != "reference":
            return

        self.validate_clone_fields()

        if not self.clone_button.isEnabled():
            return

        if (
            self.clone_worker is not None
            and self.clone_worker.isRunning()
        ):
            return

        self.clone_button.setEnabled(False)
        self.clone_button.setText("Generating...")

        self.loading_label.show()
        self.loading_frame_index = 0
        self.loading_label.setText("◐ Generating...")
        self.loading_timer.start(120)

        self.status.setText(
            "Generating cloned speech. Please wait..."
        )

        self.clone_worker = CloneWorker(
            ref_audio=self.selected_file_path,
            ref_text=self.exact_text.text().strip(),
            speech_to_generate=self.speech_to_generate.text().strip(),
        )

        self.clone_worker.finished_successfully.connect(
            self.clone_succeeded
        )
        self.clone_worker.failed.connect(self.clone_failed)
        self.clone_worker.finished.connect(self.cleanup_worker)

        self.clone_worker.start()

    def animate_loading(self):
        self.loading_frame_index = (
            self.loading_frame_index + 1
        ) % len(self.loading_frames)

        frame = self.loading_frames[self.loading_frame_index]
        self.loading_label.setText(f"{frame} Generating...")

    def clone_succeeded(self, output_path):
        self.loading_timer.stop()
        self.loading_label.hide()

        self.generated_file_path = os.path.abspath(output_path)
        filename = Path(self.generated_file_path).name

        # Update the path label to mirror the Selected file formatting
        self.generated_file_label.setText(
            f"Generated clone: {filename}\n{self.generated_file_path}"
        )
        self.generated_file_label.setToolTip(
            self.generated_file_path
        )

        self.generated_play_button.setEnabled(
            os.path.isfile(self.generated_file_path)
        )
        self.generated_play_button.setText("Play")

        self.clone_button.setText("Clone")
        self.status.setText("Voice cloned successfully.")

        self.validate_clone_fields()

    def clone_failed(self, error_message):
        self.loading_timer.stop()
        self.loading_label.hide()

        self.clone_button.setText("Clone")
        self.status.setText("Voice generation failed.")

        QMessageBox.critical(
            self,
            "Voice Generation Failed",
            error_message,
        )

        self.validate_clone_fields()

    def cleanup_worker(self):
        worker = self.clone_worker
        self.clone_worker = None

        if worker is not None:
            worker.deleteLater()

        if self.kind == "reference":
            self.validate_clone_fields()

    def toggle_playback(self, file_path=None, button=None):
        if not file_path or not os.path.isfile(file_path):
            return

        if button is None:
            button = self.play_button

        current_url = self.audio_player.source().toLocalFile()
        playback_state = self.audio_player.playbackState()

        if (
            current_url == file_path
            and playback_state
            == QMediaPlayer.PlaybackState.PlayingState
        ):
            self.audio_player.pause()
            button.setText("Resume")
            return

        if (
            current_url == file_path
            and playback_state
            == QMediaPlayer.PlaybackState.PausedState
        ):
            self.audio_player.play()
            button.setText("Pause")
            return

        self.audio_player.setSource(QUrl.fromLocalFile(file_path))
        self.audio_player.play()
        button.setText("Pause")

        if file_path == self.generated_file_path:
            self.status.setText(
                f"Playing generated clone: {Path(file_path).name}"
            )
        else:
            self.status.setText(f"Playing: {Path(file_path).name}")

    def update_play_button(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if (
                self.generated_file_path
                and self.audio_player.source().toLocalFile()
                == self.generated_file_path
            ):
                self.generated_play_button.setText("Pause")
            elif hasattr(self, "play_button"):
                self.play_button.setText("Pause")

        elif state == QMediaPlayer.PlaybackState.PausedState:
            if (
                self.generated_file_path
                and self.audio_player.source().toLocalFile()
                == self.generated_file_path
            ):
                self.generated_play_button.setText("Resume")
            elif hasattr(self, "play_button"):
                self.play_button.setText("Resume")

        elif state == QMediaPlayer.PlaybackState.StoppedState:
            if hasattr(self, "play_button"):
                self.play_button.setText("Play")

            if hasattr(self, "generated_play_button"):
                self.generated_play_button.setText("Play")

    def handle_playback_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            self.status.setText(f"Playback error: {error_string}")

            if hasattr(self, "play_button"):
                self.play_button.setText("Play")

            if hasattr(self, "generated_play_button"):
                self.generated_play_button.setText("Play")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Voice Tools")
        self.resize(1180, 1000)
        self.setMinimumSize(760, 650)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        page = QWidget()
        page.setObjectName("page")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 32)
        layout.setSpacing(24)
        layout.setAlignment(
            Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop
        )

        self.voice_cloner = AudioCard("Voice Cloner", "reference")
        self.voice_manipulator = AudioCard(
            "Voice Manipulator",
            "manipulator",
        )

        self.voice_cloner.setMaximumWidth(1000)
        self.voice_manipulator.setMaximumWidth(1000)

        layout.addWidget(self.voice_cloner)
        layout.addWidget(self.voice_manipulator)
        layout.addStretch()

        scroll.setWidget(page)
        self.setCentralWidget(scroll)
        self.centralWidget().setObjectName("centralWidget")

        self.statusBar().showMessage(
            "Choose a file or drag an audio file into either drop zone."
        )

    def selected_paths(self):
        return {
            "reference_audio": self.voice_cloner.selected_file_path,
            "manipulator_audio": self.voice_manipulator.selected_file_path,
        }


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Inter", 10))
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()