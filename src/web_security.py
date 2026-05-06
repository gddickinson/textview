"""Web security: download requests, feature permissions, certificate errors,
and per-file local-remote-access trust.

`WebSecurityHandler` attaches to the active `QWebEngineProfile` and
`QWebEnginePage`, prompting the user before granting anything potentially
dangerous. A small per-file trust set is persisted in QSettings so the user
isn't pestered repeatedly for the same trusted local file.
"""
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, QSettings
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile, QWebEnginePage, QWebEngineDownloadRequest,
    QWebEngineSettings,
)


_FEATURE_LABELS = {
    QWebEnginePage.Feature.Geolocation: "Read your location",
    QWebEnginePage.Feature.MediaAudioCapture: "Use the microphone",
    QWebEnginePage.Feature.MediaVideoCapture: "Use the camera",
    QWebEnginePage.Feature.MediaAudioVideoCapture: "Use the microphone and camera",
    QWebEnginePage.Feature.MouseLock: "Lock the mouse pointer",
    QWebEnginePage.Feature.DesktopVideoCapture: "Capture your screen",
    QWebEnginePage.Feature.DesktopAudioVideoCapture: "Capture your screen and audio",
    QWebEnginePage.Feature.Notifications: "Show desktop notifications",
}


class WebSecurityHandler(QObject):
    """One handler per MainWindow. Wires page-level signals at construction
    time and re-applies profile-level settings on demand.
    """

    def __init__(self, window, web_view):
        super().__init__(window)
        self.window = window
        self.web_view = web_view
        self._connected_pages = set()
        self._connect_profile()
        self._connect_page(web_view.engine.page())

    # -- profile-level wiring (downloads + persistent settings) --------------

    def _connect_profile(self):
        profile = QWebEngineProfile.defaultProfile()
        profile.downloadRequested.connect(self._on_download)

    def apply_profile_settings(self, d, force_remote: bool | None = None):
        """Translate DisplaySettings → QWebEngineSettings + cookie policy.

        `force_remote=True` overrides the user's default to allow remote
        URLs for the next load (used when a per-file trust grant is in
        effect). After the load completes, MainWindow re-applies with
        `force_remote=None` to revert.
        """
        profile = QWebEngineProfile.defaultProfile()
        s = profile.settings()
        remote = d.web_local_remote_access if force_remote is None else bool(force_remote)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, d.web_javascript)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, remote)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, d.web_local_file_access)
        s.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, d.web_insecure_content)
        # Cookies: persistent vs session
        try:
            mode = (
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
                if d.web_persistent_cookies
                else QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            profile.setPersistentCookiesPolicy(mode)
        except AttributeError:
            pass
        # Apply default zoom factor
        try:
            self.web_view.engine.setZoomFactor(float(d.web_default_zoom))
        except Exception:
            pass

    # -- page-level wiring ---------------------------------------------------

    def _connect_page(self, page):
        if page in self._connected_pages:
            return
        self._connected_pages.add(page)
        page.featurePermissionRequested.connect(
            lambda origin, feat, p=page: self._on_feature(p, origin, feat)
        )
        page.certificateError.connect(self._on_cert_error)

    # -- handlers ------------------------------------------------------------

    def _on_download(self, item: QWebEngineDownloadRequest):
        suggested = item.downloadFileName() or "download"
        path, _ = QFileDialog.getSaveFileName(self.window, "Save download", suggested)
        if not path:
            item.cancel()
            return
        p = Path(path)
        item.setDownloadDirectory(str(p.parent))
        item.setDownloadFileName(p.name)
        item.accept()
        self.window.statusBar().showMessage(f"Downloading → {path}", 4000)

    def _on_feature(self, page, origin: QUrl, feature):
        label = _FEATURE_LABELS.get(feature, str(feature))
        ret = QMessageBox.question(
            self.window, "Site permission requested",
            f"{origin.toString()}\n\nwants to: {label}\n\nAllow?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        grant = (
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            if ret == QMessageBox.StandardButton.Yes
            else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
        )
        page.setFeaturePermission(origin, feature, grant)

    def _on_cert_error(self, error):
        try:
            host = error.url().host()
            desc = error.description()
        except Exception:
            host, desc = "unknown", "Certificate validation failed"
        ret = QMessageBox.warning(
            self.window, "Certificate problem",
            f"{host}\n\n{desc}\n\nProceed anyway? Only do this on networks you trust.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                error.acceptCertificate()
            except AttributeError:
                error.ignoreCertificateError()
        else:
            try:
                error.rejectCertificate()
            except AttributeError:
                pass

    # -- per-file trust for local-remote-access -----------------------------

    @staticmethod
    def is_path_trusted_for_remote(path: str) -> bool:
        s = QSettings()
        trusted = set(s.value("web/local_remote_trusted", []) or [])
        return str(Path(path).resolve()) in trusted

    @staticmethod
    def trust_path_for_remote(path: str):
        s = QSettings()
        trusted = set(s.value("web/local_remote_trusted", []) or [])
        trusted.add(str(Path(path).resolve()))
        s.setValue("web/local_remote_trusted", list(trusted))

    @staticmethod
    def html_references_remote(path: str) -> bool:
        """Cheap regex scan: does the local file include any http(s) src/href?"""
        import re
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return bool(re.search(r"""(?i)(?:src|href)\s*=\s*['"]https?://""", text))

    def consult_local_remote(self, path: str, d) -> bool:
        """Decide whether to allow remote URLs for `path` on this load.

        Returns True if remote access is OK. Three sources of truth, in
        order: (1) the user's global "always allow" setting, (2) a per-file
        trust grant, (3) interactive prompt with [Once / Always / No].
        """
        if d.web_local_remote_access:
            return True
        if not self.html_references_remote(path):
            return False
        if self.is_path_trusted_for_remote(path):
            return True
        msg = QMessageBox(self.window)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Allow remote URLs?")
        msg.setText(
            f"<b>{Path(path).name}</b> wants to load scripts or stylesheets "
            "from remote URLs (CDNs, etc.)."
        )
        msg.setInformativeText(
            "Local HTML pages that fetch remote resources can leak data to "
            "third-party servers. Only allow this for files you trust."
        )
        b_once = msg.addButton("Allow once", QMessageBox.ButtonRole.AcceptRole)
        b_always = msg.addButton("Always for this file", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("No", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is b_always:
            self.trust_path_for_remote(path)
            return True
        return clicked is b_once
