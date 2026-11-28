# 모핑 시네마틱 버전 (비교용)

최종제출본(`docs/final/submission/`)과 같은 내용·수치를 25장 모핑 전환으로 다시 구성한 별도 버전입니다. 사용자가 채택하기 전까지 최종제출본은 바뀌지 않습니다.

- 생성: `node docs/final/src/build_morph.js morph_raw.pptx` 후 `python3 docs/final/src/morph_post.py morph_raw.pptx out.pptx` (모든 슬라이드에 Morph 전환 삽입, 지원하지 않는 프로그램은 Fade로 대체)
- 데이터: `experiments/main30/summary.csv`, `runs.csv`, 간트용 `gantt_replan.json` (빌드 시 수치 검사)
- 영상 자리: 13장
- 모핑은 PowerPoint 2019 이상 / Microsoft 365에서만 재생됩니다.
