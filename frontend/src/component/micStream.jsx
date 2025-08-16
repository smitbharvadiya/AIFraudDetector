import React, { useEffect, useRef, useState } from "react";

const MicStreamer = () => {
    const wsRef = useRef(null);
    const [recording, setRecording] = useState(false);
    const audioChunks = useRef([]);

    useEffect(() => {
        return () => {
            if (wsRef.current) wsRef.current.close();
        };
    }, []);

    const startStopStreaming = async () => {
        if (!recording) {
            wsRef.current = new WebSocket("ws://localhost:8000/audio");
            wsRef.current.onopen = () => console.log("WebSocket Connected");
            wsRef.current.onmessage = (event) => console.log("Server:", event.data);

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const audioContext = new AudioContext();
            const source = audioContext.createMediaStreamSource(stream);

            await audioContext.audioWorklet.addModule("/processor.js");
            const processorNode = new AudioWorkletNode(audioContext, "audio-processor");

            source.connect(processorNode);
            processorNode.connect(audioContext.destination);

            processorNode.port.onmessage = (event) => {
                const floatData = event.data;
                const int16Buffer = floatTo16Bit(floatData);
                audioChunks.current.push(int16Buffer);

                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                    wsRef.current.send(int16Buffer);
                }
            };

            setRecording(true);
        } else {
            if (wsRef.current) wsRef.current.close();
            setRecording(false);

            const wavBlob = encodeWAV(audioChunks.current);
            const url = URL.createObjectURL(wavBlob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "recorded_audio.wav";
            a.click();

            URL.revokeObjectURL(url);

            audioChunks.current = [];
        }
    };

    const floatTo16Bit = (float32Array) => {
        const buffer = new ArrayBuffer(float32Array.length * 2);
        const view = new DataView(buffer);
        let offset = 0;
        for (let i = 0; i < float32Array.length; i++, offset += 2) {
            let s = Math.max(-1, Math.min(1, float32Array[i]));
            view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }
        return buffer;
    };

    const encodeWAV = (chunks) => {
        const totalLength = chunks.reduce((sum, c) => sum + c.byteLength, 0);
        const buffer = new ArrayBuffer(44 + totalLength);
        const view = new DataView(buffer);

        const writeString = (offset, str) => {
            for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
        };

        writeString(0, "RIFF");
        view.setUint32(4, 36 + totalLength, true);
        writeString(8, "WAVE");
        writeString(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 1, true);
        view.setUint32(24, 44100, true);
        view.setUint32(28, 44100 * 2, true);
        view.setUint16(32, 2, true);
        view.setUint16(34, 16, true);
        writeString(36, "data");
        view.setUint32(40, totalLength, true);

        let offset = 44;
        chunks.forEach((chunk) => {
            const chunkView = new DataView(chunk);
            for (let i = 0; i < chunk.byteLength; i++, offset++) {
                view.setUint8(offset, chunkView.getUint8(i));
            }
        });

        return new Blob([view], { type: "audio/wav" });
    };

    return (
        <div className="p-4 border rounded bg-gray-100">
            <h2 className="font-bold">🎤 Mic Streamer</h2>
            <button
                className="px-4 py-2 mt-2 bg-blue-600 text-white rounded"
                onClick={startStopStreaming}
            >
                {recording ? "Stop Recording" : "Start Recording"}
            </button>
            {recording && <p>Streaming audio to backend...</p>}
        </div>
    );
};

export default MicStreamer;
