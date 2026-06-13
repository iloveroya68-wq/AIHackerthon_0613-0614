interface DisclaimerBannerProps {
  text?: string;
}

const DEFAULT_TEXT =
  "본 시스템의 분석 결과는 의사결정 지원용이며, 최종 판단은 현장 지휘관의 책임 하에 이루어져야 합니다. AI 예측에는 오차가 포함될 수 있습니다.";

export function DisclaimerBanner({ text = DEFAULT_TEXT }: DisclaimerBannerProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-amber-400/10 border-t border-amber-400/30 text-xs text-amber-300">
      <svg
        className="shrink-0 w-4 h-4 text-amber-400"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>
      <span>{text}</span>
    </div>
  );
}
