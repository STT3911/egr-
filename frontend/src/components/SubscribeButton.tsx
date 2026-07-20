import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bell, BellRing, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { useToast } from "@/hooks/use-toast";
import {
  getCurrentUser,
  listSubscriptions,
  createSubscription,
  deleteSubscription,
  EVENT_TYPE_LABELS,
  type SubscriptionItem,
} from "@/lib/api";

const btnClass =
  "w-full glass hover:bg-primary/10 dark:hover:bg-primary/20 transition-all duration-300 text-sm sm:text-base";

export function SubscribeButton({ unp }: { unp: string | number }) {
  const unpNum = Number(unp);
  const qc = useQueryClient();
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  const meQ = useQuery({ queryKey: ["me"], queryFn: getCurrentUser, retry: false, staleTime: 60_000 });
  const isAuthed = !!meQ.data;

  const subsQ = useQuery({
    queryKey: ["subscriptions"],
    queryFn: listSubscriptions,
    enabled: isAuthed,
    retry: false,
  });
  const existing: SubscriptionItem | undefined = subsQ.data?.items.find((s) => s.unp === unpNum);

  const openDialog = () => {
    setSelected(existing?.event_types ?? []);
    setOpen(true);
  };

  const saveM = useMutation({
    mutationFn: () => createSubscription(unpNum, selected),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subscriptions"] });
      setOpen(false);
      toast({ title: "Подписка сохранена" });
    },
    onError: (e: Error) => toast({ title: "Ошибка", description: e.message, variant: "destructive" }),
  });

  const delM = useMutation({
    mutationFn: () => deleteSubscription(existing!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subscriptions"] });
      setOpen(false);
      toast({ title: "Отписка выполнена" });
    },
    onError: (e: Error) => toast({ title: "Ошибка", description: e.message, variant: "destructive" }),
  });

  if (meQ.isLoading) {
    return (
      <Button variant="outline" disabled className={btnClass}>
        <Loader2 className="h-4 w-4 animate-spin" />
      </Button>
    );
  }

  if (!isAuthed) {
    return (
      <Link to={`/login?next=/company/${unp}`} className="w-full">
        <Button variant="outline" className={btnClass}>
          <Bell className="mr-2 h-4 w-4" />
          Подписаться
        </Button>
      </Link>
    );
  }

  const toggle = (t: string) =>
    setSelected((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant={existing ? "default" : "outline"} onClick={openDialog} className={btnClass}>
        {existing ? <BellRing className="mr-2 h-4 w-4" /> : <Bell className="mr-2 h-4 w-4" />}
        {existing ? "Подписка активна" : "Подписаться"}
      </Button>

      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Подписка на события компании</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Отметьте интересующие события. Если ничего не выбрано — будут все события.
        </p>
        <div className="grid max-h-80 gap-2 overflow-auto py-1">
          {Object.entries(EVENT_TYPE_LABELS).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox checked={selected.includes(key)} onCheckedChange={() => toggle(key)} />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <DialogFooter className="gap-2 sm:gap-2">
          {existing && (
            <Button variant="destructive" onClick={() => delM.mutate()} disabled={delM.isPending}>
              {delM.isPending ? "…" : "Отписаться"}
            </Button>
          )}
          <Button onClick={() => saveM.mutate()} disabled={saveM.isPending}>
            {saveM.isPending ? "Сохранение…" : existing ? "Сохранить изменения" : "Подписаться"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default SubscribeButton;
