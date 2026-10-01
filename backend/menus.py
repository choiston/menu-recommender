# =============================================================================
# menus.py - 메뉴 데이터 불러오기 + 검사                         버전: test 2.0
#
# test 1.0 에서는 메뉴 50개를 이 파일 안에 파이썬 코드로 직접 적었지만,
# test 2.0 부터는 메뉴가 129개이고 정보(칼로리, 주재료, 먹는 팁, 관련 메뉴)도 많아져서
# 데이터를 data/menus.json 파일로 따로 뺐습니다.
#
#   - JSON 파일 : 데이터만 담음 (나중에 AI나 공공데이터로 다시 만들어 통째로 바꾸기 쉬움)
#   - 이 파일   : JSON 을 읽어서 파이썬에서 쓰기 좋은 모양으로 준비 + 잘못된 데이터 검사
#
# 메뉴 1개의 모양 (menus.json):
#   {
#     "name": "순대국밥",          # 이름. test 2.0 부터는 이름이 곧 고유 id 입니다 (겹치면 안 됨)
#     "emoji": "🍲",
#     "broad": false,              # true = 큰 분류 메뉴 (1라운드와 [다른 방향 보기]에 나옴)
#                                  # false = 세부 메뉴 (고른 메뉴를 따라 깊이 들어갈 때만 나옴)
#     "tags": [...],               # 특징표 (국물, 매움, 한식 ...)
#     "meals": [...],              # 어울리는 식사 시간
#     "ingredients": [...],        # 주재료 (결과 화면에 표시 + 재료 입력과 비교)
#     "kcal": 650,                 # 1인분 대략 칼로리 (추정치)
#     "tips": [...],               # 맛있게 먹는 법 2개
#     "related": [...]             # 관련 메뉴 이름들 ← "깊이 들어가기"의 핵심
#   }
# =============================================================================

import json                 # JSON 파일을 읽어서 파이썬 딕셔너리/리스트로 바꿔 주는 표준 라이브러리
from pathlib import Path    # 파일 경로를 다루는 표준 라이브러리 (윈도우/리눅스 경로 차이를 알아서 처리)

# 메뉴 "종류" 태그 목록. 메뉴마다 이 중 딱 1개를 가져야 합니다.
# set(집합) 자료형: 중복이 없고, "in" 으로 포함 여부를 아주 빠르게 확인할 수 있음
CATEGORIES = {"한식", "중식", "일식", "양식", "분식", "아시안", "패스트푸드"}

# 데이터 파일 위치.
# __file__ = 지금 이 파일(menus.py)의 경로 → .parent = 들어 있는 폴더(backend) → / "data" / "menus.json"
# 이렇게 하면 서버를 어느 폴더에서 실행하든 항상 올바른 파일을 찾습니다.
DATA_PATH = Path(__file__).parent / "data" / "menus.json"


def load_menus():
    """menus.json 을 읽고, 데이터에 실수가 없는지 검사한 뒤 메뉴 리스트를 돌려줍니다."""
    # with open(...) : 파일을 열고, 블록이 끝나면 자동으로 닫아 줌
    # encoding="utf-8" : 한글이 들어 있으므로 꼭 지정 (안 하면 윈도우에서 글자가 깨질 수 있음)
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)  # JSON 문자열 → 파이썬 딕셔너리
    menus = data["menus"]

    # ---- 데이터 검사 (데이터 검증) ----
    # 사람이(또는 AI가) 손으로 만든 데이터는 오타가 생기기 쉽습니다.
    # 서버가 켜질 때 미리 검사해서, 문제가 있으면 바로 알려 주고 멈춥니다.
    # (나중에 사용자가 클릭했을 때 이상하게 동작하는 것보다 훨씬 찾기 쉬움)
    names = [m["name"] for m in menus]
    duplicates = {n for n in names if names.count(n) > 1}   # 집합 컴프리헨션
    if duplicates:
        raise ValueError(f"메뉴 이름이 겹칩니다: {duplicates}")

    name_set = set(names)
    for m in menus:
        # 관련 메뉴(related)에 적힌 이름이 실제로 존재하는지
        missing = [r for r in m["related"] if r not in name_set]
        if missing:
            raise ValueError(f"'{m['name']}' 의 관련 메뉴 중 없는 메뉴가 있습니다: {missing}")
        # 종류 태그가 정확히 1개인지
        kinds = [t for t in m["tags"] if t in CATEGORIES]
        if len(kinds) != 1:
            raise ValueError(f"'{m['name']}' 의 종류 태그는 1개여야 합니다: {kinds}")

    return menus


# 서버가 시작될 때(이 파일이 import 될 때) 한 번만 읽어 둡니다.
MENUS = load_menus()

# 이름으로 메뉴를 바로 찾기 위한 딕셔너리.  예) MENU_BY_ID["순대국밥"] → 순대국밥 메뉴
# 딕셔너리 컴프리헨션: {키: 값 for 항목 in 리스트}
MENU_BY_ID = {menu["name"]: menu for menu in MENUS}
