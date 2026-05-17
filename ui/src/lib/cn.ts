import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Standard shadcn/ui class-name merger — used by every UI primitive.
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
