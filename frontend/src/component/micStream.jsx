
const MicStreamer = () => {
let ws;

async function startAudioStream() {
    ws = new WebSocket("ws://localhost:8000/audio");

    ws.onopen = () => {
        console.log("Websocket Connected");
        startRecording();
    }

    ws.onmessage = (e) => {
        console.log("Server:" + e.data);
    }
}

async function startRecording(){
    try{
        const stream = await navigator.mediaDevices.getUserMedia({audio:true});
        const audioContext = new AudioContext();
        const source = audioContext.createMediaStreamSource(stream);

        await audioContext.audioWorklet.addModule("/processor.js"); 
        const processorNode = new AudioWorkletNode(audioContext, "audio-processor");


        source.connect(processorNode);
        processorNode.connect(audioContext.destination);

        processorNode.port.onmessage = (event) => {
            const floatData = event.data;
            const int16Buffer = floatTo16Bit(floatData);
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(int16Buffer);
            }
        }
    } catch (err) {
        console.error("Mic error:", err);
    }
}

function floatTo16Bit(float32Array){
    const buffer = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buffer);
    let offset = 0;
    for(let i = 0; i< float32Array.length; i++, offset += 2){
        let s = Math.max(-1, Math.min(1, float32Array[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buffer;
}

startAudioStream();

return (
        <div className="p-4 border rounded bg-gray-100">
            <h2 className="font-bold">🎤 Mic Streamer</h2>
            <p>Streaming audio to backend...</p>
        </div>
    );
}
    
export default MicStreamer;
