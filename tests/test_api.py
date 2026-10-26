from fastapi.testclient import TestClient
from app.main import app

def test_endpoints():
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        hotels=client.get('/v1/hotels').json()
        assert len(hotels)==6
        response=client.post('/v1/search',json={'query':'тихий номер у моря'})
        assert response.status_code==200
        assert response.json()['results']
        assert client.get('/v1/metrics').json()['hotels']==6
        assert client.get('/v1/auth/telegram').status_code==401
        assert client.post('/v1/agent/chat',json={'message':'с питомцем'}).status_code==200

def test_hotelier_flow():
    with TestClient(app) as client:
        questions=client.get('/v1/hotelier/1/questions').json()
        answer=client.post(f"/v1/hotelier/questions/{questions[0]['id']}/answer",json={'text':'В номерах есть шумоизоляция'})
        assert answer.status_code==200
        assert answer.json()['value'] is True
