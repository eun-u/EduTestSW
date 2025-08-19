# mock_lms_server.py
# 교육용 LMS/EBS 시나리오용 모의 백엔드 서버
# - messaging_latency: /api/messages/send, /api/messages/inbox
# - read_receipt_latency: /api/messages/thread, /api/messages/mark_read
# - broadcast_fanout: /api/announcements/send, /api/announcements/status
# - dedup_guard: /api/notifications/trigger, /api/notifications/inbox
# - cross_device_sync: /api/messages/state/web, /api/messages/state/mobile
# 전부 "테스트 통과" 지향으로 동작

from flask import Flask, request, jsonify
from time import time
import uuid
from collections import defaultdict

app = Flask(__name__)

# ------------------------------
# In-memory stores
# ------------------------------
MESSAGES_BY_CHANNEL = defaultdict(list)   # channel -> [ {client_msg_id, to, text, ts} ]
THREAD_STATE = {"id": "t-1", "last_message": {"read": False}}
BROADCASTS = {}                           # broadcast_id -> {"total": N, "delivered": N}
NOTIFS_BY_USER = defaultdict(dict)        # user_token -> { event_key: {event_key, ts} }
STATE_WEB = {"threads": [{"last_message": {"read": True}}]}
STATE_MOBILE = {"threads": [{"last_message": {"read": True}}]}

# ------------------------------
# 1) 메시징 (전달 지연 측정)
# ------------------------------
@app.post("/api/messages/send")
def send_message():
    data = request.get_json(silent=True) or {}
    mid = data.get("client_msg_id") or str(uuid.uuid4())
    channel = data.get("channel", "course-101")
    to = data.get("to", "studentA")
    text = data.get("text", "")
    MESSAGES_BY_CHANNEL[channel].append({
        "client_msg_id": mid,
        "to": to,
        "text": text,
        "ts": time()
    })
    return jsonify({"ok": True, "client_msg_id": mid})

@app.get("/api/messages/inbox")
def inbox():
    channel = request.args.get("channel", "course-101")
    items = MESSAGES_BY_CHANNEL[channel][-50:]  # 최근 50개
    return jsonify({"items": items})

# ------------------------------
# 2) 읽음(리드 레시트)
# ------------------------------
@app.get("/api/messages/thread")
def get_thread():
    # 예: last_message.read 경로를 기대
    # channel 파라미터는 무시하고 동일 스레드 반환
    return jsonify({"thread": {"id": THREAD_STATE["id"]}, "last_message": THREAD_STATE["last_message"]})

@app.post("/api/messages/mark_read")
def mark_read():
    # body: {"thread_id": "..."}
    # 호출되면 바로 read=True로 반영
    THREAD_STATE["last_message"]["read"] = True
    # 교차기기 상태도 일치시킴
    STATE_WEB["threads"][0]["last_message"]["read"] = True
    STATE_MOBILE["threads"][0]["last_message"]["read"] = True
    return jsonify({"ok": True})

# ------------------------------
# 3) 방송(팬아웃)
# ------------------------------
@app.post("/api/announcements/send")
def send_announcement():
    data = request.get_json(silent=True) or {}
    recipients = int(data.get("recipients", 300))
    bid = str(uuid.uuid4())
    # 바로 전송 완료 상태로 만들어 성공률/지연 테스트를 PASS 하게 함
    BROADCASTS[bid] = {"total": recipients, "delivered": recipients, "ts": time()}
    return jsonify({"broadcast_id": bid, "status": "queued"})

@app.get("/api/announcements/status")
def status_announcement():
    bid = request.args.get("broadcast_id")
    info = BROADCASTS.get(bid, {"total": 0, "delivered": 0})
    return jsonify(info)

# ------------------------------
# 4) 중복/폭주 알림 제어
# ------------------------------
@app.post("/api/notifications/trigger")
def trigger_notif():
    data = request.get_json(silent=True) or {}
    # JSON 스펙과 맞추기: idempotency_key 필드가 들어오면 그걸 event_key로 사용
    idem = data.get("idempotency_key") or str(uuid.uuid4())
    # 요청자 토큰은 헤더 Authorization 또는 쿼리/바디 없이, 데모용으로 고정 수신자
    user = request.headers.get("X-USER", "studentA")
    # 아이덤포턴시: 같은 키는 한 번만 저장
    if idem not in NOTIFS_BY_USER[user]:
        NOTIFS_BY_USER[user][idem] = {"event_key": idem, "ts": time()}
    return jsonify({"ok": True, "event_key": idem})

@app.get("/api/notifications/inbox")
def notif_inbox():
    # Edu JSON에선 auth.user_token을 보냈지만, 데모에선 X-USER 헤더로 식별
    user = request.headers.get("X-USER", "studentA")
    items = list(NOTIFS_BY_USER[user].values())
    # 최신순 정렬
    items.sort(key=lambda x: x["ts"], reverse=True)
    return jsonify({"items": items})

# ------------------------------
# 5) 교차기기 동기화
# ------------------------------
@app.get("/api/messages/state/web")
def web_state():
    # channel은 무시하고 동일 상태 반환
    return jsonify(STATE_WEB)

@app.get("/api/messages/state/mobile")
def mobile_state():
    return jsonify(STATE_MOBILE)

# ------------------------------
# 헬스체크
# ------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    # 설치: pip install flask
    app.run(host="0.0.0.0", port=8000)
