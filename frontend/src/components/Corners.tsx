export default function Corners({
  className = "border-white/20",
}: {
  className?: string;
}) {
  return (
    <>
      <span className={`pointer-events-none absolute top-3 right-3 h-2 w-2 border-t border-r ${className}`} />
      <span className={`pointer-events-none absolute top-3 left-3 h-2 w-2 border-t border-l ${className}`} />
      <span className={`pointer-events-none absolute bottom-3 right-3 h-2 w-2 border-b border-r ${className}`} />
      <span className={`pointer-events-none absolute bottom-3 left-3 h-2 w-2 border-b border-l ${className}`} />
    </>
  );
}
