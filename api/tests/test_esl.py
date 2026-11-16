"""ESL framing must withstand split or coalesced TCP reads."""
from app.provision import ESLFrames

class SocketStub:
    def __init__(self, chunks):
        self.chunks = list(chunks)
    def recv(self, size):
        return self.chunks.pop(0) if self.chunks else b""

def test_split_api_response_body():
    stub = SocketStub([b"Content-Type: api/response\nContent-Length: 3\n\n", b"+", b"OK"])
    h, body = ESLFrames(stub).read()
    assert h["content-type"] == "api/response"
    assert body == b"+OK"

def test_pipelined_esl_frames():
    payload = (
        b"Content-Type: auth/request\n\n"
        b"Content-Type: command/reply\nReply-Text: +OK accepted\n\n"
        b"Content-Type: api/response\nContent-Length: 3\n\n+OK"
    )
    reader = ESLFrames(SocketStub([payload]))
    assert reader.read()[0]["content-type"] == "auth/request"
    assert reader.read()[0]["reply-text"] == "+OK accepted"
    assert reader.read()[1] == b"+OK"

def test_reject_invalid_length_and_truncated_body():
    for chunks in ([b"Content-Length: nope\n\n"], [b"Content-Length: 5\n\nx"]):
        try:
            ESLFrames(SocketStub(chunks)).read()
        except (ValueError, ConnectionError):
            pass
        else:
            raise AssertionError("Invalid ESL response accepted")
