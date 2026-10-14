import { Icon } from '../components/Icon'

// 정보 화면: AI 생성 안내와 쓰인 자료의 라이선스·출처. 법적 표기라 숨기지 않는다.
export function About({ onBack }: { onBack: () => void }) {
  return (
    <div className="screen about">
      <header className="about-head">
        <button type="button" className="btn about-back" onClick={onBack}>
          <span className="btn-label"><Icon name="arrow-left" />돌아가기</span>
        </button>
        <h1>정보 · 라이선스</h1>
      </header>

      <section className="paper about-block" aria-labelledby="about-ai">
        <h2 id="about-ai">AI 생성 안내</h2>
        <p>등장인물 사진은 AI로 생성한 가상의 인물이며, 실존 인물과 관계없습니다. NPC의 대사도 AI가 만든 것입니다.</p>
      </section>

      <section className="paper about-block" aria-labelledby="about-credits">
        <h2 id="about-credits">사용한 자료</h2>
        <dl className="about-list">
          <div>
            <dt>사진 생성 모델</dt>
            <dd>FLUX.2 klein 4B (Black Forest Labs) · Apache License 2.0</dd>
          </div>
          <div>
            <dt>아이콘</dt>
            <dd>
              Phosphor Icons 2.1.1 · MIT License ·{' '}
              <a href="/licenses/phosphor-icons-MIT.txt" target="_blank" rel="noreferrer">라이선스 전문</a>
            </dd>
          </div>
          <div>
            <dt>글꼴</dt>
            <dd>
              IBM Plex Sans KR (IBM) · SIL Open Font License 1.1 ·{' '}
              <a href="/licenses/ibm-plex-sans-kr-OFL.txt" target="_blank" rel="noreferrer">라이선스 전문</a>
            </dd>
            <dd>
              Nanum Gothic Coding (NHN) · SIL Open Font License 1.1 ·{' '}
              <a href="/licenses/nanum-gothic-coding-OFL.txt" target="_blank" rel="noreferrer">라이선스 전문</a>
            </dd>
          </div>
          <div>
            <dt>종이 질감</dt>
            <dd>
              &quot;Beige paper texture&quot; Teddy (rawpixel) · CC0 1.0 (표기 의무는 없지만 밝힙니다) ·{' '}
              <a href="https://www.rawpixel.com/image/6153836/beige-paper-texture-simple-background-design" target="_blank" rel="noreferrer">출처</a>
            </dd>
          </div>
        </dl>
      </section>
    </div>
  )
}
