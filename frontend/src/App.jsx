import { useEffect, useState } from "react";

function App() {
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    const socket = new WebSocket("ws://127.0.0.1:8000/ws");
    socket.onmessage = (event) => {
      setMessages(prev => [...prev, JSON.parse(event.data)]);
    };
    return () => socket.close();
  }, []);

  return (
    <div>
      <h1>Risk Data (WebSocket)</h1>
      <pre>{JSON.stringify(messages, null, 2)}</pre>
    </div>
  );
}

export default App;
