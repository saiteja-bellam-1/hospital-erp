import React from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "./dialog"
import { Button } from "./button"

/**
 * A reusable confirmation dialog to replace window.confirm().
 *
 * Usage:
 *   const [confirmState, setConfirmState] = useState({ open: false });
 *   const confirm = (message, onConfirm) =>
 *     setConfirmState({ open: true, message, onConfirm });
 *
 *   <ConfirmDialog
 *     open={confirmState.open}
 *     message={confirmState.message}
 *     onConfirm={() => { confirmState.onConfirm?.(); setConfirmState({ open: false }); }}
 *     onCancel={() => setConfirmState({ open: false })}
 *   />
 */
const ConfirmDialog = ({
  open,
  title = "Confirm",
  message = "Are you sure?",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "destructive",
  onConfirm,
  onCancel,
}) => {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onCancel?.(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant={variant} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export { ConfirmDialog }
