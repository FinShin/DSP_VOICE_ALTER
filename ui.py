import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSlider, QVBoxLayout, QWidget
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


APP_STYLE = """
* { box-sizing: border-box; }
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
    """Drop audio files here or use Choose File. Stores the selected absolute path."""

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
        layout.addWidget(self.choose_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.selected_name)

    def choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an audio file",
            str(Path.home()),
            "Audio files (*.mp3 *.wav *.ogg *.oga *.m4a *.aac *.flac *.webm *.opus);;All files (*)",
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


class AudioCard(QFrame):
    def __init__(self, title, kind="reference"):
        super().__init__()
        self.setObjectName("card")
        self.setProperty("class", "card")
        self.kind = kind
        self.selected_file_path = ""
        self.audio_output = QAudioOutput(self)
        self.audio_player = QMediaPlayer(self)
        self.audio_player.setAudioOutput(self.audio_output)
        self.audio_player.errorOccurred.connect(self.handle_playback_error)
        self.audio_player.playbackStateChanged.connect(self.update_play_button)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 28, 30, 30)
        outer.setSpacing(18)

        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(heading)

        if kind == "reference":
            outer.addWidget(self.field_label("Add a voice reference"))
            self.drop_zone = DropZone(self.set_selected_file)
            outer.addWidget(self.drop_zone)
            outer.addWidget(self.field_label("Record instead"))
            outer.addLayout(self.record_row())
            self.status = QLabel("")
            self.status.setObjectName("muted")
            outer.addWidget(self.status)
            self.exact_text = QLineEdit()
            self.exact_text.setPlaceholderText("Exact speech (text) said on the audio given")
            outer.addWidget(self.exact_text)
            outer.addWidget(self.selected_row("Selected file:"))
            self.speech_to_generate = QLineEdit()
            self.speech_to_generate.setPlaceholderText("Speech to generate")
            clone_row = QHBoxLayout()
            clone_row.setSpacing(10)
            clone_row.addWidget(self.speech_to_generate, 1)
            clone_button = QPushButton("Clone")
            clone_button.clicked.connect(self.show_ui_only_notice)
            clone_row.addWidget(clone_button)
            outer.addLayout(clone_row)
            outer.addWidget(self.selected_row("Generated clone:", generated=True))
            self.progress_panel = self.progress_row()
            outer.addWidget(self.progress_panel)
        else:
            outer.addWidget(self.field_label("Pick an audio file"))
            self.drop_zone = DropZone(self.set_selected_file)
            outer.addWidget(self.drop_zone)
            outer.addWidget(self.field_label("Record instead"))
            outer.addLayout(self.record_row())
            self.status = QLabel("")
            self.status.setObjectName("muted")
            outer.addWidget(self.status)
            outer.addWidget(self.selected_row("Selected file:"))
            outer.addWidget(self.progress_row())
            outer.addWidget(self.subsection("Noise Filtered", "Processed audio output", "Filtered audio:", "Not generated", "Filter"))
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
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("secondary")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stop")
        self.record_btn.clicked.connect(lambda: self.status.setText("Recording UI placeholder"))
        self.pause_btn.clicked.connect(lambda: self.status.setText("Pause / Resume UI placeholder"))
        self.stop_btn.clicked.connect(lambda: self.status.setText("Recording stopped (UI only)"))
        row.addWidget(self.record_btn)
        row.addWidget(self.pause_btn)
        row.addWidget(self.stop_btn)
        wave = QFrame()
        wave.setObjectName("wavePanel")
        wave_layout = QHBoxLayout(wave)
        wave_layout.setContentsMargins(8, 4, 8, 4)
        wave_bars = QLabel("▂ ▄ ▆ ▃ ▅ ▂ ▇ ▄ ▂ ▅ ▃ ▆ ▂ ▄ ▅ ▃ ▇ ▂ ▅ ▄ ▃ ▆")
        wave_bars.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wave_bars.setStyleSheet("color:#3b82f6; font-size:14px;")
        wave_layout.addWidget(wave_bars)
        row.addWidget(wave, 1)
        return row

    def selected_row(self, label_text, generated=False):
        panel = QFrame()
        panel.setObjectName("softPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(12)
        info = QVBoxLayout()
        info.setSpacing(4)
        if not generated:
            # Keep the selected-file heading and its value in the same label,
            # so the filename and absolute path visibly append to "Selected file:".
            file_label = self.field_label(f"{label_text} No file selected")
            file_label.setStyleSheet("font-size:12px; color:#64748b; font-weight:600;")
            file_label.setWordWrap(True)
            file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            file_label.setMinimumWidth(0)
            self.selected_file_label = file_label
            info.addWidget(file_label)
        else:
            label = self.field_label(label_text)
            label.setStyleSheet("font-size:12px;")
            info.addWidget(label)
            file_label = QLabel("No file generated")
            file_label.setObjectName("fileName")
            file_label.setWordWrap(True)
            file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            file_label.setMinimumWidth(0)
            info.addWidget(file_label)
        layout.addLayout(info, 1)
        play = QPushButton("Play")
        play.setObjectName("secondary")
        play.setMinimumWidth(76)
        play.setEnabled(False)
        if not generated:
            self.play_button = play
            play.clicked.connect(self.toggle_playback)
        layout.addWidget(play)
        return panel

    def progress_row(self):
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        start = QLabel("00:00")
        end = QLabel("00:00")
        start.setObjectName("muted")
        end.setObjectName("muted")
        track = QFrame()
        track.setFixedHeight(5)
        track.setStyleSheet("background:#e1eaf8; border-radius:3px;")
        layout.addWidget(start)
        layout.addWidget(track, 1)
        layout.addWidget(end)
        return panel

    def subsection(self, title, subtitle, label, filename, action):
        section = QFrame()
        section.setStyleSheet("QFrame { border: none; border-top: 1px solid #e9edf5; }")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(12)
        heading = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:16px; font-weight:750; color:#1e293b;")
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
        section.setStyleSheet("QFrame { border: none; border-top: 1px solid #e9edf5; }")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 20, 0, 0)
        layout.setSpacing(14)
        title = QLabel("Pitch and Volume Alter")
        title.setStyleSheet("font-size:16px; font-weight:750; color:#1e293b;")
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
        grid.addLayout(self.slider_control("Pitch", "Lower", "Normal", "Higher", 50, 200, 100, self.pitch_value))
        self.volume_value = QLabel("+100%")
        grid.addLayout(self.slider_control("Volume Boost", "Original", "+100%", "+200%", 0, 200, 100, self.volume_value))
        generate = QPushButton("Generate")
        generate.setEnabled(False)
        grid.addWidget(generate)
        layout.addWidget(controls)
        return section

    def slider_control(self, title, left, middle, right, minimum, maximum, value, value_label):
        wrapper = QVBoxLayout()
        heading = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("font-size:12px; font-weight:750; color:#35435a;")
        value_label.setStyleSheet("font-size:12px; font-weight:750; color:#2f68d4;")
        heading.addWidget(name)
        heading.addStretch()
        heading.addWidget(value_label)
        wrapper.addLayout(heading)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        if title == "Pitch":
            slider.valueChanged.connect(lambda v: value_label.setText(f"{v / 100:.2f}×"))
        else:
            slider.valueChanged.connect(lambda v: value_label.setText(f"+{v}%"))
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
            QMessageBox.warning(self, "Invalid file", "Please choose a valid local file.")
            return
        suffix = Path(path).suffix.lower()
        valid = {".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac", ".flac", ".webm", ".opus"}
        if suffix not in valid:
            QMessageBox.warning(self, "Unsupported file", "Please choose a supported audio file.")
            return
        self.audio_player.stop()
        self.selected_file_path = path
        filename = Path(path).name
        self.drop_zone.selected_name.setText(filename)
        self.selected_file_label.setText(f"Selected file: {filename}\n{path}")
        self.selected_file_label.setToolTip(path)
        self.selected_file_label.adjustSize()
        self.play_button.setEnabled(True)
        self.play_button.setText("Play")
        self.status.setText("Selected file path saved.")
        self.status.setToolTip(path)

    def toggle_playback(self):
        if not self.selected_file_path or not os.path.isfile(self.selected_file_path):
            return

        current_url = self.audio_player.source().toLocalFile()
        if current_url == self.selected_file_path and self.audio_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.audio_player.pause()
            self.play_button.setText("Resume")
            return

        if current_url == self.selected_file_path and self.audio_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.audio_player.play()
            self.play_button.setText("Pause")
            return

        self.audio_player.setSource(QUrl.fromLocalFile(self.selected_file_path))
        self.audio_player.play()
        self.play_button.setText("Pause")
        self.status.setText(f"Playing: {Path(self.selected_file_path).name}")

    def update_play_button(self, state):
        if not hasattr(self, "play_button"):
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText("Pause")
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.play_button.setText("Play")

    def handle_playback_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            self.status.setText(f"Playback error: {error_string}")
            self.play_button.setText("Play")

    def show_ui_only_notice(self):
        QMessageBox.information(
            self,
            "UI prototype",
            "This is a UI-only clone for now. The selected file's absolute path is stored in selected_file_path.",
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice Tools")
        self.resize(1180, 1000)
        self.setMinimumSize(760, 650)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 32)
        layout.setSpacing(24)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.voice_cloner = AudioCard("Voice Cloner", "reference")
        self.voice_manipulator = AudioCard("Voice Manipulator", "manipulator")
        self.voice_cloner.setMaximumWidth(1000)
        self.voice_manipulator.setMaximumWidth(1000)
        layout.addWidget(self.voice_cloner)
        layout.addWidget(self.voice_manipulator)
        layout.addStretch()

        scroll.setWidget(page)
        self.setCentralWidget(scroll)
        self.centralWidget().setObjectName("centralWidget")

        self.statusBar().showMessage("UI prototype — choose a file or drag an audio file into either drop zone.")

    def selected_paths(self):
        """Returns both selected absolute paths for future backend integration."""
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
