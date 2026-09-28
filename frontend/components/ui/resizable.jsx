"use client"

import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels"

import { cn } from "@/lib/utils"

function ResizablePanelGroup({ className, ...props }) {
  return (
    <PanelGroup
      className={cn("flex h-full w-full data-[panel-group-direction=vertical]:flex-col", className)}
      {...props}
    />
  )
}

const ResizablePanel = Panel

function ResizableHandle({ withHandle, className, ...props }) {
  return (
    <PanelResizeHandle
      className={cn(
        "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-navy data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-1 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:-translate-y-1/2 data-[panel-group-direction=vertical]:after:translate-x-0 [&[data-panel-group-direction=vertical]>div]:rotate-90",
        className
      )}
      {...props}
    >
      {withHandle ? (
        <div className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border bg-border" aria-hidden="true" />
      ) : null}
    </PanelResizeHandle>
  )
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle }
