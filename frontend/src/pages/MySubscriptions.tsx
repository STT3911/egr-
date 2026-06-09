import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, Building2 } from "lucide-react";

import { Header } from "@/components/layout/Header";
import { Footer } from "@/components/layout/Footer";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import {
  getCurrentUser,
  listSubscriptions,
  deleteSubscription,
  logoutUser,
  EVENT_TYPE_LABELS,
} from "@/lib/api";

const MySubscriptions = () => {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast } = useToast();

  const meQ = useQuery({ queryKey: ["me"], queryFn: getCurrentUser, retry: false });

  useEffect(() => {
    if (meQ.isError) {
      navigate("/login?next=/subscriptions", { replace: true });
    }
  }, [meQ.isError, navigate]);

  const subsQ = useQuery({
    queryKey: ["subscriptions"],
    queryFn: listSubscriptions,
    enabled: !!meQ.data,
    retry: false,
  });

  const delM = useMutation({
    mutationFn: (id: string) => deleteSubscription(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["subscriptions"] });
      toast({ title: "Отписка выполнена" });
    },
    onError: (e: Error) => toast({ title: "Ошибка", description: e.message, variant: "destructive" }),
  });

  const handleLogout = async () => {
    await logoutUser().catch(() => undefined);
    qc.clear();
    navigate("/", { replace: true });
  };

  const items = subsQ.data?.items ?? [];

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto max-w-3xl px-4 pt-32 pb-16">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Мои подписки</h1>
            {meQ.data?.email && (
              <p className="mt-1 text-sm text-muted-foreground">{meQ.data.email}</p>
            )}
          </div>
          <Button variant="outline" onClick={handleLogout}>Выйти</Button>
        </div>

        {(meQ.isLoading || subsQ.isLoading) && (
          <div className="flex h-32 items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        )}

        {subsQ.data && items.length === 0 && (
          <Card className="surface-card">
            <CardContent className="p-6 text-center text-muted-foreground">
              У вас пока нет подписок. Откройте карточку компании и нажмите «Подписаться».
            </CardContent>
          </Card>
        )}

        <div className="space-y-3">
          {items.map((s) => (
            <Card key={s.id} className="surface-card">
              <CardContent className="flex items-start justify-between gap-3 p-4">
                <div className="min-w-0">
                  <Link
                    to={`/company/${s.unp}`}
                    className="flex items-center gap-2 font-medium text-foreground hover:text-primary"
                  >
                    <Building2 className="h-4 w-4 shrink-0" />
                    УНП {s.unp}
                  </Link>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(s.event_types.length ? s.event_types : ["__all__"]).map((t) => (
                      <Badge key={t} variant="secondary" className="text-xs">
                        {t === "__all__" ? "Все события" : EVENT_TYPE_LABELS[t] || t}
                      </Badge>
                    ))}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-destructive hover:text-destructive"
                  onClick={() => delM.mutate(s.id)}
                  disabled={delM.isPending}
                  aria-label="Отписаться"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
      <Footer />
    </div>
  );
};

export default MySubscriptions;
