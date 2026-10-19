import { memo } from "react";

function hueFor(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) % 360;
  }
  return hash;
}

const avatarSizes = {
  xxs: "h-4 w-4 text-[8px]",
  xs: "h-8 w-8 text-[11px]",
  sm: "h-9 w-9 text-xs",
  md: "h-11 w-11 text-sm",
  lg: "h-14 w-14 text-lg",
} as const;

type AvatarSize = keyof typeof avatarSizes;

const Avatar = memo(function Avatar({
  name,
  size = "md",
  className = "",
}: {
  name: string;
  size?: AvatarSize;
  className?: string;
}) {
  const hue = hueFor(name || "?");
  return (
    <span
      className={`relative flex shrink-0 select-none items-center justify-center overflow-hidden rounded-full border border-white/20 font-bold text-white shadow-[0_0_18px_-8px_rgba(255,255,255,0.7)] ${avatarSizes[size]} ${className}`}
      style={{
        background: `linear-gradient(135deg, hsl(${hue} 55% 24%), hsl(${(hue + 45) % 360} 45% 12%))`,
      }}
      title={name}
    >
      <span className="absolute inset-0 bg-gradient-to-b from-white/10 to-transparent" />
      <span className="relative">{name?.charAt(0).toUpperCase() || "?"}</span>
    </span>
  );
});

export default Avatar;
