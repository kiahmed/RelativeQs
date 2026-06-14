type SnapshotHandler = (payload: any) => void

type QQQScoreHandler = (payload: any) => void

type PredictionHandler = (payload: any) => void

type RotationHandler = (payload: any) => void

export function createBackendClient(wsUrl = 'ws://localhost:8000/ws/market') {
  let ws: WebSocket | null = null
  let reconnect = true
  let onSnapshot: SnapshotHandler | null = null
  let onQQQScore: QQQScoreHandler | null = null
  let onPrediction: PredictionHandler | null = null
  let onRotation: RotationHandler | null = null

  function connect() {
    if (ws) return
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.debug('[backendClient] connected')
    }

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data?.type === 'snapshot' && onSnapshot) {
          onSnapshot(data.payload)
        }
        if (data?.type === 'qqq_score' && onQQQScore) {
          onQQQScore(data.payload)
        }
        if (data?.type === 'prediction' && onPrediction) {
          onPrediction(data.payload)
        }
        if (data?.type === 'rotation' && onRotation) {
          onRotation(data.payload)
        }
        // rotation may also ride along inside a snapshot payload
        if (data?.type === 'snapshot' && data.payload?.rotation && onRotation) {
          onRotation(data.payload.rotation)
        }
      } catch (e) {
        console.error('[backendClient] parse error', e)
      }
    }

    ws.onclose = () => {
      ws = null
      console.debug('[backendClient] closed')
      if (reconnect) setTimeout(connect, 1000)
    }

    ws.onerror = (err) => {
      console.error('[backendClient] error', err)
    }
  }

  function disconnect() {
    reconnect = false
    if (ws) {
      ws.close()
      ws = null
    }
  }

  function send(obj: any) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify(obj))
  }

  function onSnapshotCb(cb: SnapshotHandler | null) {
    onSnapshot = cb
  }

  function onQQQScoreCb(cb: QQQScoreHandler | null) {
    onQQQScore = cb
  }

  function onPredictionCb(cb: PredictionHandler | null) {
    onPrediction = cb
  }

  function onRotationCb(cb: RotationHandler | null) {
    onRotation = cb
  }

  return {
    connect,
    disconnect,
    send,
    onSnapshot: onSnapshotCb,
    onQQQScore: onQQQScoreCb,
    onPrediction: onPredictionCb,
    onRotation: onRotationCb,
  }
}
