/**
 * 글꼴(D30-3): IBM Plex Sans KR 자가 호스팅(@fontsource/ibm-plex-sans-kr 5.3.0, 400·500·600·700). 외부 글꼴 CDN 은 쓰지 않는다.
 *
 * fontsource 의 글자 범위(unicode-range) 조각이라 브라우저는 화면에 나온 글자의 조각 파일만 받는다. 다만 @font-face 선언만
 * 수백 개(약 230kB)라 진입 CSS 에 넣으면 첫 화면을 막는다 — AppLayout 이 첫 렌더 뒤 이 모듈을 동적 import 해 따로 붙인다
 * (font-display: swap 이라 그 전에는 시스템 한글 글꼴로 보인다). index.css 의 @import 로는 Tailwind 가 CSS 를 펼치면서
 * 글꼴 파일 상대 경로를 고치지 않아 못 쓴다.
 */
import '@fontsource/ibm-plex-sans-kr/400.css';
import '@fontsource/ibm-plex-sans-kr/500.css';
import '@fontsource/ibm-plex-sans-kr/600.css';
import '@fontsource/ibm-plex-sans-kr/700.css';

export const FONT_WEIGHTS = [400, 500, 600, 700] as const;
