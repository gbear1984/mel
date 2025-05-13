"""
==============================================================================
 SE Toolset - Arnold Batch Render Tool (W.R.O.N.G.) | Version 1.40b stable
------------------------------------------------------------------------------
 Created to make Maya a more peaceful system through clarity, control,
 and noncompliant override options for rendering workflows.

 Author: Steve Eisenmann
 Website: https://steve-eisenmann.com
 GitHub: https://github.com/gbear1984
==============================================================================

 DESCRIPTION:
 This tool allows for flexible Arnold batch rendering in Maya via GUI or
 internal W.R.O.N.G. execution. Includes:
  - Full resolution + AA control
  - Motion blur and adaptive sampling toggles
  - GPU/CPU switching
  - Custom project override
  - Live log + progress for internal (W.R.O.N.G.) rendering
  - .BAT export for external automation
  - Cancelable internal render protocol

 VERSIONING SCHEME:
 1.XXa â€” Alpha: core features prototyped
 1.XXb â€” Beta: functional integration, pending stability
 1.XXprod â€” Production ready (internal or pipeline deployable)

==============================================================================

 PYTHON IMPORTS EXPLAINED:

 os             â€” For path handling, file creation, and normalization
 subprocess     â€” Used to launch external batch renders
maya.cmds       â€” Core Maya commands (setAttr, listRelatives, etc.)
maya.mel        â€” For direct MEL-based render calls (W.R.O.N.G.)
maya.OpenMayaUI â€” To access the Qt main window for parenting GUI
PySide2.QtWidgets â€” Used to build and manage the Qt-based interface
PySide2.QtCore    â€” Needed for processEvents and live feedback
shiboken2         â€” Required to wrap Mayaâ€™s Qt window for proper parenting

==============================================================================

 CLASS OVERVIEW:

 â€¢ ArnoldRenderSettings
   - Stores and manages the current sceneâ€™s render parameters
   - Normalizes paths, generates render commands and strings
   - Used across batch and internal (W.R.O.N.G.) render modes

 â€¢ RenderBatchUI
   - Builds the full PySide2 UI
   - Connects UI to ArnoldRenderSettings and render triggers
   - Contains logic for preview updates, .bat export, and internal rendering

==============================================================================

 DEPLOYMENT:
 Save this file into your Maya scripts folder and load via:

 from arnold_batch_command_builder_1_09b import RenderBatchUI
 RenderBatchUI().show()

==============================================================================
# VERSION HISTORY - W.R.O.N.G. Render Tool
# ------------------------------------------------------------------------------
# 1.00a - Initial prototype: basic GUI, AA override, camera support.
# 1.05b - Added motion blur toggle, res multiplier, and project override.
# 1.09b - .BAT export support, adaptive AA, and GPU toggle added.
# 1.20b - Introduced per-frame ETA, render progress, pause/resume control.
# 1.30b - Added Arnold JSON log reader, stats parser, and batch log output.
# 1.35b - Integrated live JSON frame summary into the main UI.
# 1.36b - UI polishing, error catching, and file path normalization fixes.
# 1.38b - Major update: fully working auto-folder versioning system.
#         • Frames now route into v### subdirectories
#         • Auto version-up logic for new renders
#         • Specific version override toggle
#         • Bugfixes to frame movement from temp directories
# ==============================================================================
# Last Updated: 2025-05-13
# ==============================================================================

"""

import os
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui
from PySide2 import QtWidgets, QtCore
from shiboken2 import wrapInstance
import subprocess
import datetime
import json
import shutil
import glob

class ArnoldRenderSettings:
    def __init__(self):
        self.scene_path = cmds.file(q=True, sn=True)
        if not self.scene_path:
            self.scene_path = os.path.join(cmds.workspace(q=True, rd=True), "unsaved_scene.mb")

        self.scene_dir = os.path.dirname(self.scene_path)
        self.scene_name = os.path.splitext(os.path.basename(self.scene_path))[0]
        self.current_version = None
        self.version_folder = None
        self.output_version_folder = None
        try:
            self.render_dir = os.path.join(self.scene_dir, f"{self.scene_name}_renders")
            if not os.path.exists(self.render_dir):
                os.makedirs(self.render_dir)
        except PermissionError:
            fallback = os.path.join(os.environ.get("TEMP", "C:/Temp"), f"{self.scene_name}_renders")
            self.render_dir = fallback
            os.makedirs(self.render_dir, exist_ok=True)

        self.start_frame = int(cmds.getAttr("defaultRenderGlobals.startFrame"))
        self.end_frame = int(cmds.getAttr("defaultRenderGlobals.endFrame"))
        self.resolution_x = int(cmds.getAttr("defaultResolution.width"))
        self.resolution_y = int(cmds.getAttr("defaultResolution.height"))
        self.aa_samples = int(cmds.getAttr("defaultArnoldRenderOptions.AASamples"))
        self.aa_max = int(cmds.getAttr("defaultArnoldRenderOptions.AASamplesMax")) if cmds.attributeQuery("AASamplesMax", node="defaultArnoldRenderOptions", exists=True) else self.aa_samples
        self.adaptive_threshold = float(cmds.getAttr("defaultArnoldRenderOptions.AA_adaptive_threshold"))
        self.motion_blur = bool(cmds.getAttr("defaultArnoldRenderOptions.motion_blur_enable"))
        self.res_multiplier = 1.0

        render_cams = [cam for cam in cmds.ls(type='camera') if cmds.getAttr(cam + '.renderable')]
        self.camera = cmds.listRelatives(render_cams[0], parent=True)[0] if render_cams else "RENDER_CAMERA_NOT_FOUND"

        self.settings = {
            "Renderer": ("-r", "arnold"),
            "Start Frame": ("-s", str(self.start_frame)),
            "End Frame": ("-e", str(self.end_frame)),
            "Camera": ("-cam", self.camera),
            "Image Output Directory": ("-rd", self.render_dir),
            "Image Name": ("-im", self.scene_name),
            "Image Format": ("-of", "exr"),
            "Project Directory": ("-proj", ""),
            "Threads": ("-rt", "0"),
            "Verbose Level": ("-ai:lve", "2"),
        }

    def normalize_path(self, path):
        norm = os.path.normpath(path)
        return norm.replace('\\', '/') if os.name != 'nt' else norm.replace('/', '\\')

    def get_command_args(self):
        args = []
        for _, (flag, value) in self.settings.items():
            args.extend([flag, self.normalize_path(value)] if isinstance(value, str) else [flag, str(value)])
        args.append(self.normalize_path(self.scene_path))
        return args

    def get_command_string(self):
        parts = ['"Render"']
        for _, (flag, value) in self.settings.items():
            parts.append(f'{flag} "{self.normalize_path(value)}"' if isinstance(value, str) else f'{flag} {value}')
        parts.append(f'"{self.normalize_path(self.scene_path)}"')
        return " ".join(parts)

class RenderBatchUI(QtWidgets.QDialog):
    log_timer_interval = 5000  # ms
    log_pattern = None
    log_timer = None
    last_log_file = ""
    def __init__(self):
        parent = wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
        super(RenderBatchUI, self).__init__(parent)
        self.setWindowTitle("W.R.O.N.G. Batch Render Tool")
        self.setMinimumWidth(900)

        self.settings = ArnoldRenderSettings()
        self.gpu_enabled = cmds.getAttr('defaultArnoldRenderOptions.renderDevice') == 1
        self.cancelled = False
        # moved to after build_ui()
        self.paused = False

        self.build_ui()
        self.update_preview()
        self.paused = self.launch_paused_checkbox.isChecked()

    def build_ui(self):
        self.pause_hour = 8  # Default pause hour (8AM)

        outer_layout = QtWidgets.QVBoxLayout(self)
        main_layout = QtWidgets.QHBoxLayout()
        outer_layout.addLayout(main_layout)

        left_col = QtWidgets.QVBoxLayout()
        main_layout.addLayout(left_col, 3)

        self.res_label = QtWidgets.QLabel(f"Resolution: {self.settings.resolution_x} x {self.settings.resolution_y}")
        left_col.addWidget(self.res_label)

        # Add this early in build_ui() after defining the main layout
        self.version_checkbox = QtWidgets.QCheckBox("Enable File Versioning")
        self.version_checkbox.setChecked(False)
        self.version_checkbox.stateChanged.connect(self.toggle_version_fields)
        left_col.addWidget(self.version_checkbox)
        
        version_layout = QtWidgets.QHBoxLayout()
        self.version_auto_radio = QtWidgets.QRadioButton("Auto Version Up")
        self.version_specific_radio = QtWidgets.QRadioButton("Use Specific Version:")
        self.version_auto_radio.setChecked(True)
        
        version_layout.addWidget(self.version_auto_radio)
        version_layout.addWidget(self.version_specific_radio)
        
        self.version_spinbox = QtWidgets.QSpinBox()
        self.version_spinbox.setRange(1, 999)
        self.version_spinbox.setEnabled(False)
        version_layout.addWidget(self.version_spinbox)
        
        left_col.addLayout(version_layout)


        self.res_mult = QtWidgets.QDoubleSpinBox()
        self.res_mult.setRange(0.1, 4.0)
        self.res_mult.setSingleStep(0.1)
        self.res_mult.setValue(1.0)
        self.restore_resolution_btn = QtWidgets.QPushButton("Restore Original Resolution")
        self.restore_resolution_btn.clicked.connect(self.restore_original_resolution)
        left_col.addWidget(self.restore_resolution_btn)
        left_col.addWidget(QtWidgets.QLabel("Resolution Multiplier:"))
        left_col.addWidget(self.res_mult)

        self.aa_spin = QtWidgets.QSpinBox()
        self.aa_spin.setRange(1, 99)
        self.aa_spin.setValue(self.settings.aa_samples)
        left_col.addWidget(QtWidgets.QLabel("AA Samples:"))
        left_col.addWidget(self.aa_spin)

        self.max_aa_spin = QtWidgets.QSpinBox()
        self.max_aa_spin.setRange(1, 99)
        self.max_aa_spin.setValue(self.settings.aa_max)
        left_col.addWidget(QtWidgets.QLabel("Max AA Samples (UI only):"))
        left_col.addWidget(self.max_aa_spin)

        self.adaptive_threshold_field = QtWidgets.QDoubleSpinBox()
        self.adaptive_threshold_field.setDecimals(3)
        self.adaptive_threshold_field.setRange(0.0, 5.0)
        self.adaptive_threshold_field.setSingleStep(0.001)
        self.adaptive_threshold_field.setValue(self.settings.adaptive_threshold)
        left_col.addWidget(QtWidgets.QLabel("AA Adaptive Threshold:"))
        left_col.addWidget(self.adaptive_threshold_field)

        self.motion_blur_toggle = QtWidgets.QCheckBox("Enable Motion Blur")
        self.motion_blur_toggle.setChecked(self.settings.motion_blur)
        left_col.addWidget(self.motion_blur_toggle)

        self.start_frame_field = QtWidgets.QSpinBox()
        self.start_frame_field.setRange(-100000, 100000)
        self.start_frame_field.setValue(self.settings.start_frame)
        left_col.addWidget(QtWidgets.QLabel("Start Frame:"))
        left_col.addWidget(self.start_frame_field)

        self.end_frame_field = QtWidgets.QSpinBox()
        self.end_frame_field.setRange(-100000, 100000)
        self.end_frame_field.setValue(self.settings.end_frame)
        left_col.addWidget(QtWidgets.QLabel("End Frame:"))
        left_col.addWidget(self.end_frame_field)

        self.device_toggle = QtWidgets.QCheckBox("Use GPU Rendering")
        self.device_toggle.setChecked(self.gpu_enabled)
        left_col.addWidget(self.device_toggle)

        self.override_proj_checkbox = QtWidgets.QCheckBox("Use Scene Folder as Project Directory")
        self.override_proj_checkbox.setToolTip("Use the folder where your current scene is saved as the render output and project directory.")
        self.override_proj_checkbox.setChecked(True)
        self.project_dir_checkbox = QtWidgets.QCheckBox("Use Custom Project Directory")
        self.project_dir_checkbox.setToolTip("Specify a custom folder for your project render outputs.")
        self.project_dir_checkbox.setChecked(False)
        self.project_dir_field = QtWidgets.QLineEdit()
        self.project_dir_field.setToolTip("Path to the custom project directory used for rendering.")
        self.project_dir_field.setPlaceholderText("Choose custom project directory...")
        self.project_dir_field.setEnabled(False)
        self.project_dir_button = QtWidgets.QPushButton("Browse")
        self.project_dir_button.setEnabled(False)

        def toggle_custom_project():
            enabled = self.project_dir_checkbox.isChecked()
            self.project_dir_field.setEnabled(enabled)
            self.project_dir_button.setEnabled(enabled)

        def choose_directory():
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Project Directory", cmds.workspace(q=True, rd=True))
            if folder:
                self.project_dir_field.setText(folder)

        self.project_dir_checkbox.toggled.connect(toggle_custom_project)
        self.project_dir_button.clicked.connect(choose_directory)

        # Preview selected project directory
        self.project_dir_preview = QtWidgets.QLabel()
        self.project_dir_preview.setStyleSheet("color: gray; font-style: italic;")
        left_col.addWidget(QtWidgets.QLabel("Render Output Path Preview:"))
        left_col.addWidget(self.project_dir_preview)

        left_col.addWidget(self.override_proj_checkbox)
        left_col.addWidget(self.project_dir_checkbox)
        left_col.addWidget(self.project_dir_field)
        left_col.addWidget(self.project_dir_button)

        self.cmd_preview = QtWidgets.QTextEdit()
        self.cmd_preview.setReadOnly(True)
        self.cmd_preview.setMinimumHeight(50)
        left_col.addWidget(QtWidgets.QLabel("Render Command Preview:"))
        left_col.addWidget(self.cmd_preview)

        left_col.addWidget(self._button("Update Preview", self.update_preview))
        left_col.addWidget(self._button("Render", self.execute_render))
        left_col.addWidget(self._button("Write .BAT File", self.write_bat_file))

        self.log_output = QtWidgets.QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(80)
        left_col.addWidget(QtWidgets.QLabel("Live Render Log:"))
        left_col.addWidget(self.log_output)

        self.progress = QtWidgets.QProgressBar()
        left_col.addWidget(self.progress)

        btn_layout = QtWidgets.QHBoxLayout()
        self.wrong_btn = QtWidgets.QPushButton("W.R.O.N.G. Render")
        self.wrong_btn.clicked.connect(self.internal_maya_render)
        btn_layout.addWidget(self.wrong_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel Render")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_render)
        btn_layout.addWidget(self.cancel_btn)

        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setEnabled(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        btn_layout.addWidget(self.pause_btn)

        self.pause_reason_label = QtWidgets.QLabel("Render status: Active")
        self.pause_reason_label.setStyleSheet("color: gray; font-style: italic;")
        left_col.addWidget(self.pause_reason_label)

                # Auto-pause configuration
        self.pause_hour_spin = QtWidgets.QDoubleSpinBox()
        self.pause_hour_spin.setDecimals(1)
        self.pause_hour_spin.setSingleStep(0.1)
        self.pause_hour_spin.setRange(0.0, 23.9)
        self.pause_hour_spin.setValue(self.pause_hour)

        self.pause_enable_checkbox = QtWidgets.QCheckBox("Enable Auto-Pause")
        self.pause_enable_checkbox.setChecked(True)
        self.pause_enable_checkbox.toggled.connect(lambda checked: self.pause_hour_spin.setEnabled(checked))
        self.pause_hour_spin.setEnabled(True)

        self.resume_enable_checkbox = QtWidgets.QCheckBox("Enable Auto-Resume")
        self.resume_enable_checkbox.setChecked(True)

        self.resume_hour_spin = QtWidgets.QDoubleSpinBox()
        self.resume_hour_spin.setDecimals(1)
        self.resume_hour_spin.setSingleStep(0.1)
        self.resume_hour_spin.setRange(0.0, 23.9)
        self.resume_hour_spin.setValue(self.pause_hour + 1 if self.pause_hour < 23 else 0)
        self.launch_paused_checkbox = QtWidgets.QCheckBox("Launch Paused")
        self.launch_paused_checkbox.setToolTip("If checked, rendering starts in a paused state until resumed manually or by schedule.")
        self.launch_paused_checkbox.setChecked(False)
        self.resume_hour_spin.setEnabled(True)

        self.resume_enable_checkbox.toggled.connect(lambda checked: self.resume_hour_spin.setEnabled(checked))
        self.pause_enable_checkbox.setChecked(True)

        label_pause = QtWidgets.QLabel("Auto-Pause Hour (0-23):")
        label_pause.setStyleSheet("color: red; font-weight: bold;")
        left_col.addWidget(self.pause_enable_checkbox)
        left_col.addWidget(label_pause)
        left_col.addWidget(self.pause_hour_spin)

        self.resume_hour_spin = QtWidgets.QDoubleSpinBox()
        self.resume_hour_spin.setDecimals(1)
        self.resume_hour_spin.setSingleStep(0.1)
        self.resume_hour_spin.setRange(0.0, 23.9)
        self.resume_hour_spin.setValue(self.pause_hour + 1 if self.pause_hour < 23 else 0)
        label_resume = QtWidgets.QLabel("Auto-Resume Hour (0-23):")
        label_resume.setStyleSheet("color: green; font-weight: bold;")
        left_col.addSpacing(10)
        left_col.addWidget(self.resume_enable_checkbox)
        left_col.addWidget(label_resume)
        left_col.addWidget(self.resume_hour_spin)

        
        

        left_col.addLayout(btn_layout)
        left_col.addWidget(self.launch_paused_checkbox)

        # removed redundant toggle_log_checkbox setup


        log_label = QtWidgets.QLabel("Detailed Arnold Render Log")
        log_label.setStyleSheet("font-weight: bold; font-size: 8pt;")
        log_group_widget = QtWidgets.QWidget()
        self.log_group_widget = log_group_widget
        log_group = QtWidgets.QVBoxLayout(log_group_widget)
        log_group.addWidget(log_label)
        self.batch_log_output = QtWidgets.QTextEdit()
        self.batch_log_output.setReadOnly(True)
        self.batch_log_output.setMinimumWidth(500)
        self.batch_log_output.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        log_group.addWidget(self.batch_log_output)
        clear_btn = QtWidgets.QPushButton("Clear Log")
        clear_btn.clicked.connect(lambda: self.batch_log_output.clear())
        log_group.addWidget(clear_btn)
        main_layout.insertWidget(1, log_group_widget, 1)
        # moved into log_group above
 #############################################################################
    def toggle_version_fields(self):
        enabled = self.version_checkbox.isChecked()
        self.version_auto_radio.setEnabled(enabled)
        self.version_specific_radio.setEnabled(enabled)
        self.version_spinbox.setEnabled(enabled and self.version_specific_radio.isChecked())

    def get_next_version_number(self, output_dir, base_name):
        import re
        pattern = re.compile(rf"{re.escape(base_name)}_v(\d{{3}})\.\d{{4}}\.exr")
        versions = [int(m.group(1)) for f in os.listdir(output_dir)
                    if (m := pattern.search(f))]
        return max(versions + [0]) + 1 if versions else 1

    def construct_output_filename(self, base_name, frame):
        return os.path.join(self.version_folder, f"{base_name}.{frame:04d}.exr")

        if self.version_specific_radio.isChecked():
            version = self.version_spinbox.value()
        else:
            version = self.get_next_version_number(output_dir, base_name)

        return f"{base_name}_v{version:03d}.{frame:04d}.exr"

    def move_render_to_output(self, tmp_path, _unused_output_dir, base_name, frame):
        filename = self.construct_output_filename(base_name, frame)
        dest_path = filename  # already full path
        try:
            shutil.move(tmp_path, dest_path)
            self.log(f"Moved: {tmp_path} -> {dest_path}")
        except Exception as e:
            self.log(f"[Error] Moving frame {frame}: {e}")

 #################################################################################
    def _button(self, label, callback):
        btn = QtWidgets.QPushButton(label)
        btn.clicked.connect(callback)
        return btn

    def log(self, message):
        self.log_output.append(message)
        QtCore.QCoreApplication.processEvents()

    def log_batch(self, message):
        self.batch_log_output.append(message)
        QtCore.QCoreApplication.processEvents()

    def start_log_watcher(self):
        if not self.log_pattern:
            return
        self.log_timer = QtCore.QTimer()
        self.log_timer.timeout.connect(self.read_latest_stats_log)
        self.log_timer.start(self.log_timer_interval)

    def stop_log_watcher(self):
        if self.log_timer:
            self.log_timer.stop()
            self.log_timer.deleteLater()
            self.log_timer = None

    def read_latest_stats_log(self):
        files = sorted(glob.glob(self.log_pattern), key=os.path.getmtime)
        if not files:
            return

        latest = files[-1]
        try:
            with open(latest, 'r') as f:
                data = json.load(f)

            # Find the highest numbered render log (e.g., render 0000)
            render_keys = [k for k in data.keys() if k.startswith('render')]
            latest_render_key = sorted(render_keys)[-1] if render_keys else None
            render_data = data.get(latest_render_key, {})

            frame_path_key = f"{os.path.basename(latest)}:{latest_render_key}:{os.path.getmtime(latest)}"

            if frame_path_key == self.last_log_file:
                return
            self.last_log_file = frame_path_key

            mem = render_data.get('peak CPU memory used', {}).get('bytes', 'N/A')
            if isinstance(mem, int):
                mem = f"{round(mem / (1024 ** 2))} MB"

            ray_data = render_data.get('ray counts', {}).get('total', {})
            rays = ray_data.get('ray count', 'N/A')
            render_time_us = render_data.get('frame time', {}).get('microseconds', 0)
            render_time = round(render_time_us / 1_000_000, 2) if render_time_us else 'N/A'

            frame_id = latest_render_key.split()[-1] if latest_render_key else "Unknown"

            summary = f"[Stats] Frame {frame_id}: Time {render_time}s | Memory {mem} | Rays {rays}"
            self.log_batch(summary)

            def flatten_dict(d, prefix=''):
                lines = []
                for k, v in d.items():
                    if isinstance(v, dict):
                        lines.extend(flatten_dict(v, prefix + k + '/'))
                    else:
                        lines.append(f"{prefix + k}: {v}")
                return lines

            self.log_batch("===== Arnold Stats Summary =====")
            for key, section in render_data.items():
                if key == "ray counts" or key == "shader calls" or key == "geometry" or key == "geometric elements" or key == "acceleration structures":
                    self.log_batch(f"  {key}:")
                    if isinstance(section, dict):
                        for subkey, subval in section.items():
                            self.log_batch(f"    {subkey}:")
                            if isinstance(subval, dict):
                                for stat_key, stat_val in subval.items():
                                    self.log_batch(f"      {stat_key}: {stat_val}")
                            else:
                                self.log_batch(f"      {subval}")
            self.log_batch("===== End of Stats Summary =====")

        except Exception as e:
            self.log_batch(f"[Stats] Failed to read: {e}")

        QtCore.QCoreApplication.processEvents()
        QtCore.QCoreApplication.processEvents()

    def cancel_render(self):
        self.cancelled = True
        self.log("Render cancel requested by user.")
        self.cancel_btn.setEnabled(False)
        self.wrong_btn.setEnabled(True)

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.setText("Resume" if self.paused else "Pause")
        self.pause_reason_label.setText("Render status: Paused (manual)" if self.paused else "Render status: Active")
        self.log("Render paused." if self.paused else "Resuming render.")

    def execute_render(self):
        render_path = r"C:\Program Files\Autodesk\Maya2024\bin\Render.exe"
        proj_dir = self.project_dir_field.text() if self.project_dir_checkbox.isChecked() else (self.settings.scene_dir if self.override_proj_checkbox.isChecked() else cmds.workspace(q=True, rd=True))
        self.settings.settings["Project Directory"] = ("-proj", proj_dir)
        os.environ['MTOA_RENDER_DEVICE'] = 'GPU' if self.device_toggle.isChecked() else 'CPU'
        full_cmd = [render_path] + self.settings.get_command_args()

        self.log_batch("Starting external Arnold render...")
        try:
            proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            for line in proc.stdout:
                self.log_batch(line.strip())
            proc.wait()

            if proc.returncode != 0:
                self.log_batch(f"Render.exe exited with error code {proc.returncode}")
                QtWidgets.QMessageBox.critical(self, "Render Failed", f"Render.exe failed with code {proc.returncode}")
            else:
                self.log_batch("Render.exe finished successfully.")
        except Exception as e:
            self.log_batch(f"Error launching render: {e}")
            QtWidgets.QMessageBox.critical(self, "Render Error", f"Render failed:{e}")


    def write_bat_file(self):
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save .BAT File", self.settings.scene_name + ".bat", "Batch Files (*.bat)")
        if not filepath:
            return

        render_path = r"C:\Program Files\Autodesk\Maya2024\bin\Render.exe"
        proj_dir = self.project_dir_field.text() if self.project_dir_checkbox.isChecked() else (self.settings.scene_dir if self.override_proj_checkbox.isChecked() else cmds.workspace(q=True, rd=True))
        self.settings.settings["Project Directory"] = ("-proj", proj_dir)
        args = self.settings.get_command_args()
        cmd_line = f'"{render_path}" ' + " ".join(f'"{a}"' if " " in a else a for a in args)
        mtoa_env = "set MTOA_RENDER_DEVICE=GPU" if self.device_toggle.isChecked() else "set MTOA_RENDER_DEVICE=CPU"

        try:
            with open(filepath, "w") as f:
                f.write("@echo off")
                f.write(f"{mtoa_env}")
                f.write(f"{cmd_line}")
                f.write("pause")
            QtWidgets.QMessageBox.information(self, "Batch File Saved", f".BAT file written to:{filepath}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Write Failed", f"Could not write BAT file:{e}")

    def internal_maya_render(self):
        self.start_log_watcher()
        
        base_dir = self.settings.render_dir
        base_name = self.settings.scene_name
    
        def get_next_version_folder(base):
            for i in range(1, 1000):
                candidate = os.path.join(base, f"v{i:03d}")
                if not os.path.exists(candidate):
                    return candidate, i
            return os.path.join(base, "v999"), 999  # fallback
    
        # Determine version folder based on user selection
        if self.version_checkbox.isChecked():
            if self.version_specific_radio.isChecked():
                ver = self.version_spinbox.value()
                version_folder = os.path.join(base_dir, f"v{ver:03d}")
            else:
                version_folder, ver = get_next_version_folder(base_dir)
    
            os.makedirs(version_folder, exist_ok=True)
            self.output_version_folder = version_folder
        else:
            self.output_version_folder = base_dir  # No versioning
    
        ###output_dir = self.output_version_folder  # <- used below
        self.render_start_time = datetime.datetime.now()
        import time
        import shutil
    
        self.cancelled = False
        self.cancel_btn.setEnabled(True)
        self.wrong_btn.setEnabled(False)

        if cmds.window("renderViewWindow", exists=True):
            try:
                cmds.deleteUI("renderViewWindow", window=True)
                self.log("Closed RenderView window to prevent crashes.")
            except:
                self.log("Warning: could not close RenderView.")

        start = self.start_frame_field.value()
        end = self.end_frame_field.value()
        cam = self.settings.camera
        total_frames = end - start + 1
        self.progress.setMaximum(total_frames)
        self.progress.setValue(0)

        ##cmds.workspace(fileRule=['images', output_dir])
        cmds.workspace(fileRule=['images', self.settings.render_dir])
        cmds.workspace(saveWorkspace=True)
        start_time = time.time()
        frame_times = []
        base_dir = self.settings.render_dir
        base_name = self.settings.scene_name
        
        def get_next_version_folder(base):
            for i in range(1, 1000):
                candidate = os.path.join(base, f"v{i:03d}")
                if not os.path.exists(candidate):
                    return candidate, i
            return os.path.join(base, "v999"), 999  # fallback
        
        # Determine version folder before rendering
        if self.version_checkbox.isChecked():
            if self.version_specific_radio.isChecked():
                ver = self.version_spinbox.value()
            else:
                _, ver = get_next_version_folder(base_dir)
            self.current_version = ver
            self.version_folder = os.path.join(base_dir, f"v{ver:03d}")
            os.makedirs(self.version_folder, exist_ok=True)
        else:
            self.version_folder = base_dir
        
        self.output_version_folder = self.version_folder
        output_dir = self.output_version_folder
        #####################################################################

        for i, frame in enumerate(range(start, end + 1), 1):
            if self.cancelled:
                self.log(f"Render aborted at frame {frame}.")
                break

            now = datetime.datetime.now()
            if self.pause_enable_checkbox.isChecked():
                current_time = now.hour + now.minute / 60.0
                pause_time = self.pause_hour_spin.value()
                if current_time < pause_time:
                    pause_time += 24
                launch_time = self.render_start_time.hour + self.render_start_time.minute / 60.0
                if launch_time < pause_time <= current_time and not self.paused:
                    self.log(f"Auto-pausing: it is after {self.pause_hour_spin.value():.1f}.")
                    self.paused = True
                    self.pause_btn.setText("Resume")
                    self.pause_reason_label.setText("Render status: Paused (auto)")

            while self.paused:
                QtCore.QCoreApplication.processEvents()
                time.sleep(0.5)
                if self.resume_enable_checkbox.isChecked():
                    now = datetime.datetime.now()
                    if (now.hour + now.minute / 60.0) >= self.resume_hour_spin.value():
                        if self.paused and not self.pause_btn.isEnabled():
                            self.log(f"Auto-resuming: it is after {self.resume_hour_spin.value():.1f}.")
                            self.paused = False
                            self.pause_btn.setText("Pause")
                            self.pause_reason_label.setText("Render status: Active")
                            break

            msg = f"Rendering frame {frame} with camera {cam}..."
            self.log(msg)
            self.log_batch(msg)
            frame_start = time.time()
            cmds.currentTime(frame)
            mel.eval(f'arnoldRender -cam "{cam}" {frame};')

            duration = time.time() - frame_start
            frame_times.append(duration)
            avg_time = sum(frame_times) / len(frame_times)
            frames_remaining = total_frames - i
            remaining_seconds = int(avg_time * frames_remaining)
            eta_timestamp = time.localtime(start_time + sum(frame_times) + remaining_seconds)

            hrs, rem = divmod(remaining_seconds, 3600)
            mins, _ = divmod(rem, 60)
            eta_str = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"
            finish_time_str = time.strftime("%H:%M", eta_timestamp)
            self.log(f"Frame {frame} done in {round(duration, 2)} sec — ETA: {eta_str} (finishing ~{finish_time_str})")
            self.log_batch(f"Frame {frame} done in {round(duration, 2)} sec — ETA: {eta_str} (finishing ~{finish_time_str})")

            tmp_dir = os.path.join(self.settings.render_dir, "tmp")
            if os.path.exists(tmp_dir):
                for file in os.listdir(tmp_dir):
                    if file.lower().endswith(".exr"):
                        src = os.path.join(tmp_dir, file)
                        self.move_render_to_output(src, output_dir, self.settings.scene_name, frame)

            self.progress.setValue(i)
            self.read_latest_stats_log()
            QtCore.QCoreApplication.processEvents()

        self.cancel_btn.setEnabled(False)
        self.wrong_btn.setEnabled(True)
        if not self.cancelled:
            self.stop_log_watcher()
            total_time = time.time() - start_time
            mins, secs = divmod(int(total_time), 60)
            hrs, mins = divmod(mins, 60)
            self.log(f"W.R.O.N.G. Render complete in {hrs}h {mins}m {secs}s.")
            self.log_batch(f"W.R.O.N.G. Render complete in {hrs}h {mins}m {secs}s.")


    def restore_original_resolution(self):
        width = self.settings.resolution_x
        height = self.settings.resolution_y
        cmds.setAttr("defaultResolution.width", width)
        cmds.setAttr("defaultResolution.height", height)
        self.res_mult.setValue(1.0)
        self.res_label.setText(f"Resolution: {width} x {height}")
        self.log("Restored original resolution.")

    def update_preview(self):
        # Set up stats log path for watcher
        stats_dir = os.path.join(self.settings.render_dir, "logs")
        if not os.path.exists(stats_dir):
            os.makedirs(stats_dir)
        self.log_pattern = os.path.join(stats_dir, f"{self.settings.scene_name}.*.arnold_stats*")

        # Enable Arnold render statistics logging
        stats_path = os.path.join(stats_dir, f"{self.settings.scene_name}.arnold_stats")
        cmds.setAttr("defaultArnoldRenderOptions.stats_enable", 1)
        cmds.setAttr("defaultArnoldRenderOptions.stats_file", stats_path, type="string")

        mult = self.res_mult.value()
        self.settings.res_multiplier = mult

        width = int(cmds.getAttr("defaultResolution.width") * mult)
        height = int(cmds.getAttr("defaultResolution.height") * mult)
        cmds.setAttr("defaultResolution.width", width)
        cmds.setAttr("defaultResolution.height", height)
        self.settings.resolution_x = width
        self.settings.resolution_y = height

        self.settings.aa_samples = self.aa_spin.value()
        self.settings.aa_max = self.max_aa_spin.value()
        self.settings.adaptive_threshold = self.adaptive_threshold_field.value()
        self.settings.motion_blur = self.motion_blur_toggle.isChecked()

        cmds.setAttr("defaultArnoldRenderOptions.AASamples", self.settings.aa_samples)
        if cmds.attributeQuery("AASamplesMax", node="defaultArnoldRenderOptions", exists=True):
            cmds.setAttr("defaultArnoldRenderOptions.AASamplesMax", self.settings.aa_max)
        cmds.setAttr("defaultArnoldRenderOptions.AA_adaptive_threshold", self.settings.adaptive_threshold)
        cmds.setAttr("defaultArnoldRenderOptions.motion_blur_enable", self.settings.motion_blur)

        self.settings.start_frame = self.start_frame_field.value()
        self.settings.end_frame = self.end_frame_field.value()
        cmds.setAttr("defaultRenderGlobals.startFrame", self.settings.start_frame)
        cmds.setAttr("defaultRenderGlobals.endFrame", self.settings.end_frame)

        self.settings.settings["Start Frame"] = ("-s", str(self.settings.start_frame))
        self.settings.settings["End Frame"] = ("-e", str(self.settings.end_frame))

        proj_dir = self.project_dir_field.text() if self.project_dir_checkbox.isChecked() else (self.settings.scene_dir if self.override_proj_checkbox.isChecked() else cmds.workspace(q=True, rd=True))
        self.settings.settings["Project Directory"] = ("-proj", proj_dir)

        self.res_label.setText(f"Resolution: {self.settings.resolution_x} x {self.settings.resolution_y}")
        gpu_flag = "MTOA_RENDER_DEVICE=GPU" if self.device_toggle.isChecked() else "MTOA_RENDER_DEVICE=CPU"
        self.cmd_preview.setText(f"{gpu_flag} {self.settings.get_command_string()}")
        self.project_dir_preview.setText(proj_dir)

if __name__ == "__main__":
    try:
        ui.close()
        ui.deleteLater()
    except:
        pass
    ui = RenderBatchUI()
    ui.show()


