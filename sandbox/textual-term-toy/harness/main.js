import { open } from 'rioterm';

const errEl = document.getElementById('err');
window.addEventListener('error', (e) => { errEl.textContent += `error: ${e.message}\n`; });
window.addEventListener('unhandledrejection', (e) => { errEl.textContent += `reject: ${e.reason}\n`; });

const ws = new WebSocket('ws://127.0.0.1:8765');
ws.binaryType = 'arraybuffer';

const handle = await open(document.getElementById('term'), {
  renderer: 'canvas',
  fit: true,
});
const term = handle.terminal;

ws.onmessage = (e) => term.write(new Uint8Array(e.data));
ws.onclose = () => { errEl.textContent += 'ws closed\n'; };

term.onData((data) => {
  if (ws.readyState === WebSocket.OPEN) ws.send(data);
});

// Relay grid resizes (fit tracks the container) to the PTY.
let lastCols = term.cols, lastRows = term.rows;
setInterval(() => {
  if (term.cols !== lastCols || term.rows !== lastRows) {
    lastCols = term.cols; lastRows = term.rows;
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ resize: [term.cols, term.rows] }));
    }
  }
}, 250);
