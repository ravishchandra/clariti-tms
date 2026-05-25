import Image from "next/image";
import { cn } from "@/lib/cn";
import logoMark from "@/app/icon.png";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 select-none", className)}>
      <Image
        src={logoMark}
        alt="ClaritiTMS"
        width={24}
        height={24}
        className="rounded-md"
        priority
      />
      <span className="font-semibold tracking-tight text-[var(--color-text)]">
        ClaritiTMS
      </span>
    </span>
  );
}
