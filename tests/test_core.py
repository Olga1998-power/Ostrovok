import sqlite3
from app.core import add_fact, connect, extract_answer, haversine, init_database, quality, resolve_fact, search_hotels

def test_distance():
    assert haversine(43.5791,39.7205,43.5738,39.7149)>0
    assert haversine(43.5791,39.7205,43.5791,39.7205)==0

def test_extract():
    assert extract_answer('Разрешаем собак до 10 кг','pet_max_kg')==10.0
    assert extract_answer('Можно с кошкой','pets_allowed') is True
    assert extract_answer('К сожалению, с животными нельзя','pets_allowed') is False
    assert extract_answer('Доплата 1500 руб.','pet_fee_rub')==1500
    assert extract_answer('Окна на запад','window_direction')=='west'

def test_seed_search_conflict(tmp_path):
    path=tmp_path/'demo.sqlite'
    init_database(path)
    with connect(path) as db:
        results=search_hotels(db,'тихий номер с видом на закат рядом с морем')
        assert len(results)==6
        assert results[0]['score']>=results[-1]['score']
        assert 'water_distance_m' in results[0]['hotel']['facts']
        assert quality(db)['hotels']==6
        assert add_fact(db,1,'quiet',False,'hotelier:answer')=='conflict'
        assert quality(db)['conflicts']>=1
        resolve_fact(db,1,'quiet',False)
        assert quality(db)['conflicts']==0
