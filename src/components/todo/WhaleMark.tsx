/* 手绘鲸鱼涂鸦：页头吉祥物 & 空状态插画 */

interface WhaleMarkProps {
  className?: string
}

export default function WhaleMark({ className }: WhaleMarkProps) {
  return (
    <svg viewBox="0 0 132 88" className={className} role="img" aria-label="鲸鱼涂鸦">
      {/* 水柱 */}
      <path
        d="M58 16 C55 11 53 8 50 5 M66 14 C66 9 67 6 69 2 M74 16 C77 11 80 9 83 7"
        fill="none"
        stroke="hsl(var(--border))"
        strokeWidth="3"
        strokeLinecap="round"
      />
      {/* 身体 */}
      <path
        d="M12 52 C12 34 34 22 58 22 C86 22 104 36 104 50 C104 62 86 68 60 68 C34 68 12 64 12 52 Z"
        fill="hsl(var(--secondary))"
        stroke="hsl(var(--border))"
        strokeWidth="3.5"
      />
      {/* 尾巴 */}
      <path
        d="M104 46 C110 38 116 34 122 28 C120 38 116 42 114 48 C112 54 108 58 102 58"
        fill="hsl(var(--secondary))"
        stroke="hsl(var(--border))"
        strokeWidth="3.5"
        strokeLinejoin="round"
      />
      {/* 肚皮虚线 */}
      <path
        d="M20 56 C36 62 76 63 94 57"
        fill="none"
        stroke="hsl(var(--border))"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="1 7"
      />
      {/* 眼睛 */}
      <circle cx="36" cy="42" r="3.4" fill="hsl(var(--border))" />
      {/* 腮红 */}
      <ellipse cx="26" cy="50" rx="5" ry="3" fill="#F5A9B8" opacity="0.7" />
      {/* 微笑 */}
      <path
        d="M30 50 q7 6 15 3"
        fill="none"
        stroke="hsl(var(--border))"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      {/* 鱼鳍 */}
      <path
        d="M62 66 C64 72 68 75 74 76 C70 68 68 64 66 62"
        fill="hsl(var(--secondary))"
        stroke="hsl(var(--border))"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      {/* 气泡 */}
      <circle cx="118" cy="14" r="3" fill="none" stroke="hsl(var(--border))" strokeWidth="2" />
      <circle cx="126" cy="24" r="2" fill="none" stroke="hsl(var(--border))" strokeWidth="2" />
    </svg>
  )
}
