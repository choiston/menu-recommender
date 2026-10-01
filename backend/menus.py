# =============================================================================
# menus.py - 메뉴 데이터 준비 (DB에서 읽기 + 데이터 검사)                 버전: test 3.0
#
# 데이터가 흘러가는 길
#   test 2.x : data/menus.json  ──(서버 시작 시 읽기)──> 메모리(MENUS)
#   test 3.0 : data/menus.json  ──(DB가 비어 있을 때 한 번만, seed)──> PostgreSQL DB
#              PostgreSQL DB    ──(서버 시작 시 읽기)──> 메모리(MENUS)
#
# 이제 메뉴 정보의 "원본"은 DB입니다. menus.json 은 처음 DB를 채울 때 쓰는 시작 데이터예요.
# 추천 로직(recommender.py)은 계산이 빨라야 해서, DB를 매번 묻지 않고 메모리에 올려 둔 MENUS 를 씁니다.
#
# 메뉴 1개의 모양 (메모리에서):
#   {"name": "순대국밥", "emoji": "🍲", "broad": False,
#    "tags": ["한식", "국물", ...],   ← 맨 앞이 종류 (한식, 멕시칸 ...)
#    "meals": [...], "ingredients": [...], "kcal": 650, "kcal_source": "추정치",
#    "tips": [...], "related": [...]}
# =============================================================================

import db

# 메뉴 "종류" 목록. 메뉴마다 이 중 딱 1개를 가져야 합니다.
# test 3.0 : 멕시칸, 인도·중동, 브런치·카페 추가 (7개 → 10개)
CATEGORIES = ["한식", "분식", "중식", "일식", "양식", "패스트푸드", "아시안", "멕시칸", "인도·중동", "브런치·카페"]

# 메모리에 올려 둔 메뉴 목록과, 이름으로 바로 찾는 딕셔너리.
# 처음엔 비어 있고, 서버가 켜질 때 init() 이 채웁니다.
# (다른 파일이 "from menus import MENUS" 로 가져가도 같은 리스트를 가리키므로, 나중에 채워도 보입니다)
MENUS = []
MENU_BY_ID = {}


def validate(menus):
    """메뉴 데이터에 실수가 없는지 검사합니다. 문제가 있으면 바로 에러를 내고 멈춤 (데이터 검증)"""
    names = [m["name"] for m in menus]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"메뉴 이름이 겹칩니다: {duplicates}")

    name_set = set(names)
    for m in menus:
        missing = [r for r in m["related"] if r not in name_set]
        if missing:
            raise ValueError(f"'{m['name']}' 의 관련 메뉴 중 없는 메뉴가 있습니다: {missing}")
        kinds = [t for t in m["tags"] if t in CATEGORIES]
        if len(kinds) != 1:
            raise ValueError(f"'{m['name']}' 의 종류 태그는 1개여야 합니다: {kinds}")


def init():
    """서버가 켜질 때 한 번 실행: DB 준비 → (비어 있으면) 시작 데이터 넣기 → 메뉴를 메모리로 읽기

    반환: (DB에 새로 넣은 메뉴 수, 메모리에 올린 메뉴 수)
    """
    db.wait_for_db()        # DB 컨테이너가 준비될 때까지 기다림
    db.init_schema()        # 표 만들기 (이미 있으면 건너뜀)

    seed = db.load_seed_file()
    validate(seed)          # 시작 데이터 검사
    inserted = db.seed_menus(seed, CATEGORIES)

    loaded = db.fetch_menus()
    validate(loaded)        # DB에서 읽은 데이터도 한 번 더 검사 (누군가 DB를 직접 고쳤을 수도 있으니까)

    # 리스트/딕셔너리를 "새로 만들지 않고" 내용만 바꿈 → 다른 파일이 들고 있는 참조가 그대로 유효
    MENUS.clear()
    MENUS.extend(loaded)
    MENU_BY_ID.clear()
    MENU_BY_ID.update({m["name"]: m for m in loaded})
    return inserted, len(loaded)
