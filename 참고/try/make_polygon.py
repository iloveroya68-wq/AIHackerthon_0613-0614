from shapely.geometry import Point, box

print("데모 전용 '목포 해역' Bounding Box 충돌 로직 로드 완료!")

# 기획서 LKP 기준: 목포북항 (경도 126.3668, 위도 34.8146)
# 인근 주요 육지 및 섬을 네모 박스로 단순화 (min_lon, min_lat, max_lon, max_lat)
demo_islands = [
    box(126.370, 34.780, 126.450, 34.860), # 1. 목포시 본토 (북항 동쪽 전체 막힘)
    box(126.220, 34.820, 126.350, 34.900), # 2. 압해도 (북항 북서쪽 거대한 섬)
    box(126.300, 34.750, 126.365, 34.780), # 3. 고하도 및 허사도 (북항 남쪽 방파제 역할)
    box(126.400, 34.700, 126.500, 34.780)  # 4. 영암군 본토 (남동쪽 육지)
]

def is_stranded(lon, lat):
    """
    입자의 현재 위치(lon, lat)가 육지(목포 본토 또는 섬) 위에 있는지 판별합니다.
    True면 육지 충돌(표류 멈춤), False면 바다(계속 표류).
    """
    p = Point(lon, lat)
    return any(island.contains(p) for island in demo_islands)

# ---- 테스트용 로직 ----
# 1. 기획서 상 조난 위치 인근 (바다)
test_sea = Point(126.360, 34.810)
# 2. 목포시청 인근 (육지)
test_mokpo_land = Point(126.390, 34.810) 
# 3. 압해도 내부 (육지)
test_aphaedo = Point(126.280, 34.850)

print(f"목포 앞바다는 육지인가요? : {is_stranded(test_sea.x, test_sea.y)} (정상: False)")
print(f"목포 본토는 육지인가요? : {is_stranded(test_mokpo_land.x, test_mokpo_land.y)} (정상: True)")
print(f"압해도는 육지인가요? : {is_stranded(test_aphaedo.x, test_aphaedo.y)} (정상: True)")