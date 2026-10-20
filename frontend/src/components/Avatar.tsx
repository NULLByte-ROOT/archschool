import { memo } from "react";
import type { KeyboardEvent, MouseEvent } from "react";
import { resolveMediaUrl } from "../api/client";
import { openImageViewer } from "./ImageViewer";

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
  xl: "h-24 w-24 text-3xl",
} as const;

type AvatarSize = keyof typeof avatarSizes;

const Avatar = memo(function Avatar({
  name,
  size = "md",
  src,
  className = "",
  onClick,
}: {
  name: string;
  size?: AvatarSize;
  src?: string | null;
  className?: string;
  onClick?: () => void;
}) {
  const hue = hueFor(name || "?");
  const media = resolveMediaUrl(src);
  const canOpenViewer = Boolean(media);
  const interactive = canOpenViewer || Boolean(onClick);

  function handleClick(event: MouseEvent<HTMLSpanElement>) {
    if (canOpenViewer) {
      event.stopPropagation();
      openImageViewer(media, name);
      return;
    }
    onClick?.();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLSpanElement>) {
    if (!canOpenViewer && !onClick) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    if (canOpenViewer) {
      openImageViewer(media, name);
    } else {
      onClick?.();
    }
  }

  return (
    <span
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={`avatar relative flex aspect-square shrink-0 select-none items-center justify-center overflow-hidden rounded-full border border-white/20 font-bold text-white shadow-[0_0_18px_-8px_rgba(255,255,255,0.7)] ${avatarSizes[size]} ${className} ${
        interactive ? "cursor-pointer" : ""
      }`}
      style={{
        background: `linear-gradient(135deg, hsl(${hue} 55% 24%), hsl(${(hue + 45) % 360} 45% 12%))`,
      }}
      title={name}
    >
      {media ? (
        <img
          src={media}
          alt={name}
          loading="lazy"
          decoding="async"
          className="absolute inset-0 aspect-square h-full w-full rounded-full object-cover"
        />
      ) : (
        <>
          <span className="absolute inset-0 bg-gradient-to-b from-white/10 to-transparent" />
          <span className="relative">{name?.charAt(0).toUpperCase() || "?"}</span>
        </>
      )}
    </span>
  );
});

export default Avatar;

