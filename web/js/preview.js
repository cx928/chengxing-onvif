// 摄像机预览：优先 WebRTC（MediaMTX WHEP），失败自动回退到快照
import { webrtcBase, snapshotUrl } from './api.js';

export class CameraPreview {
  constructor(container, { path, cameraId, webrtcPort }) {
    this.container = container;
    this.path = path;
    this.cameraId = cameraId;
    this.webrtcPort = webrtcPort;
    this.pc = null;
    this.video = null;
    this.fallbackTimer = null;
    this.closed = false;
  }

  async start() {
    if (!this.path || !this.webrtcPort) return this.startFallback();
    try {
      const video = document.createElement('video');
      video.muted = true;
      video.autoplay = true;
      video.playsInline = true;
      video.style.width = '100%';
      video.style.height = '100%';
      video.style.objectFit = 'cover';
      this.video = video;
      this.container.innerHTML = '';
      this.container.append(video);

      const pc = new RTCPeerConnection({ iceServers: [] });
      this.pc = pc;
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });
      const remote = new MediaStream();
      pc.ontrack = (event) => {
        event.streams[0]?.getTracks().forEach((track) => remote.addTrack(track));
        if (!video.srcObject) video.srcObject = remote;
        video.play().catch(() => {});
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const url = `${webrtcBase(this.webrtcPort)}/${this.path}/whep`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: offer.sdp,
      });
      if (!response.ok) throw new Error(`WHEP ${response.status}`);
      const answer = await response.text();
      await pc.setRemoteDescription({ type: 'answer', sdp: answer });

      const timeout = setTimeout(() => {
        if (!video.videoWidth && !this.closed) {
          this.startFallback();
        }
      }, 9000);
      pc.onconnectionstatechange = () => {
        if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) {
          clearTimeout(timeout);
          if (!this.closed) this.startFallback();
        }
      };
    } catch {
      this.startFallback();
    }
  }

  startFallback() {
    if (this.closed) return;
    this.stopPeer();
    this.container.innerHTML = '';
    const img = document.createElement('img');
    img.alt = 'camera';
    img.src = snapshotUrl(this.cameraId);
    img.onerror = () => {
      img.style.display = 'none';
      const tip = document.createElement('div');
      tip.className = 'placeholder';
      tip.innerHTML = '<div>暂无画面<br>请启动摄像机</div>';
      this.container.append(tip);
    };
    this.container.append(img);
    this.fallbackTimer = setInterval(() => {
      if (this.closed) return;
      img.src = snapshotUrl(this.cameraId);
    }, 4000);
  }

  stopPeer() {
    if (this.pc) {
      try { this.pc.close(); } catch { /* ignore */ }
      this.pc = null;
    }
  }

  stop() {
    this.closed = true;
    clearInterval(this.fallbackTimer);
    this.stopPeer();
  }
}

export function previewPlaceholder(text = '预览未启动') {
  return `<div class="placeholder">${text}</div>`;
}
