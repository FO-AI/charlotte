import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy",
  {
    variants: {
      variant: {
        default: "border-transparent bg-navy text-white",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "text-foreground",
        warning: "border-amber-300 bg-amber-50 text-amber-950",
        success: "border-emerald-300 bg-emerald-50 text-emerald-950",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({ className, variant, ...props }) {
  return (<div className={cn(badgeVariants({ variant }), className)} {...props} />);
}

export { Badge, badgeVariants }
