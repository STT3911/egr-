import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Building2,
  Clock3,
  Database,
  Download,
  FileSpreadsheet,
  Loader2,
  LogOut,
  RefreshCw,
  Search,
  Shield,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AdminDataSourceStatus,
  AdminCompanyItem,
  TradeRegistryImportRun,
  adminLogin,
  adminLogout,
  createTradeRegistryImport,
  fillCompanyFile,
  getAdminSession,
  listAdminDataSources,
  listTradeRegistryImports,
  lookupCompanies,
} from "@/lib/api";

const Admin = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [sessionUser, setSessionUser] = useState<string | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const [companies, setCompanies] = useState<AdminCompanyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [companiesLoading, setCompaniesLoading] = useState(false);
  const [companiesError, setCompaniesError] = useState<string | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [fileMessage, setFileMessage] = useState<string | null>(null);

  const [tradeRegistryFile, setTradeRegistryFile] = useState<File | null>(null);
  const [tradeRegistryRuns, setTradeRegistryRuns] = useState<TradeRegistryImportRun[]>([]);
  const [tradeRegistryLoading, setTradeRegistryLoading] = useState(false);
  const [tradeRegistryError, setTradeRegistryError] = useState<string | null>(null);

  const [dataSources, setDataSources] = useState<AdminDataSourceStatus[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);
  const [dataSourcesError, setDataSourcesError] = useState<string | null>(null);

  useEffect(() => {
    const loadSession = async () => {
      try {
        const data = await getAdminSession();
        setSessionUser(data.username);
      } catch {
        setSessionUser(null);
      } finally {
        setSessionLoading(false);
      }
    };

    loadSession();
  }, []);

  const loadTradeRegistryRuns = async () => {
    try {
      const data = await listTradeRegistryImports(5);
      setTradeRegistryRuns(data.items);
      setTradeRegistryError(null);
    } catch (err) {
      setTradeRegistryError(err instanceof Error ? err.message : "Не удалось загрузить статусы импортов");
    }
  };

  const loadDataSources = async () => {
    setDataSourcesLoading(true);
    try {
      const data = await listAdminDataSources();
      setDataSources(data.items);
      setDataSourcesError(null);
    } catch (err) {
      setDataSourcesError(err instanceof Error ? err.message : "Не удалось загрузить источники данных");
    } finally {
      setDataSourcesLoading(false);
    }
  };

  useEffect(() => {
    if (!sessionUser) {
      return;
    }
    loadTradeRegistryRuns();
    loadDataSources();
  }, [sessionUser]);

  useEffect(() => {
    if (!sessionUser || !tradeRegistryRuns.some((run) => run.status === "queued" || run.status === "running")) {
      return;
    }
    const timer = window.setInterval(() => {
      loadTradeRegistryRuns();
      loadDataSources();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [sessionUser, tradeRegistryRuns]);

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    setLoginLoading(true);
    setLoginError(null);
    try {
      const data = await adminLogin(username, password);
      setSessionUser(data.username);
      setPassword("");
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Не удалось войти");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    await adminLogout().catch(() => undefined);
    setSessionUser(null);
    setCompanies([]);
    setTotal(0);
    setAppliedQuery("");
  };

  const handleSearch = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    setAppliedQuery(trimmed);
    setCompanies([]);
    setTotal(0);

    if (!trimmed) {
      return;
    }

    setCompaniesLoading(true);
    setCompaniesError(null);
    try {
      const data = await lookupCompanies(trimmed);
      const items = data.results.map((company) => ({
        unp: company.unp,
        name: company.name || company.full_name_ru || company.short_name_ru,
        short_name: company.short_name_ru,
        address: company.address,
        status: company.status,
      }));
      setCompanies(items);
      setTotal(data.count);
    } catch (err) {
      setCompaniesError(err instanceof Error ? err.message : "Не удалось найти компании");
    } finally {
      setCompaniesLoading(false);
    }
  };

  const handleFillFile = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedFile) {
      setFileError("Выберите CSV или Excel файл");
      return;
    }

    setFileLoading(true);
    setFileError(null);
    setFileMessage(null);
    try {
      const { blob, filename } = await fillCompanyFile(selectedFile);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setFileMessage("Файл сформирован");
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Не удалось обработать файл");
    } finally {
      setFileLoading(false);
    }
  };

  const handleTradeRegistryImport = async (event: FormEvent) => {
    event.preventDefault();
    if (!tradeRegistryFile) {
      setTradeRegistryError("Выберите CSV торгового реестра");
      return;
    }

    setTradeRegistryLoading(true);
    setTradeRegistryError(null);
    try {
      const run = await createTradeRegistryImport(tradeRegistryFile);
      setTradeRegistryRuns((current) => [run, ...current.filter((item) => item.id !== run.id)].slice(0, 5));
      setTradeRegistryFile(null);
    } catch (err) {
      setTradeRegistryError(err instanceof Error ? err.message : "Не удалось запустить импорт");
    } finally {
      setTradeRegistryLoading(false);
    }
  };

  const statusLabel = (status: string) => {
    if (status === "success") return "Готово";
    if (status === "done") return "Готово";
    if (status === "failed") return "Ошибка";
    if (status === "running") return "Импорт";
    if (status === "queued") return "В очереди";
    if (status === "unknown") return "Нет данных";
    return status;
  };

  const statusVariant = (status: string): "secondary" | "destructive" | "outline" => {
    if (status === "success") return "secondary";
    if (status === "done") return "secondary";
    if (status === "failed") return "destructive";
    return "outline";
  };

  const formatDateTime = (value?: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const formatDate = (value?: string | null) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  };

  if (sessionLoading) {
    return (
      <div className="min-h-screen bg-background px-4 py-10">
        <div className="mx-auto flex min-h-[60vh] max-w-5xl items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      </div>
    );
  }

  if (!sessionUser) {
    return (
      <div className="min-h-screen bg-background px-4 py-10">
        <div className="mx-auto flex min-h-[70vh] max-w-md items-center">
          <Card className="w-full border-border/80 shadow-card">
            <CardHeader className="space-y-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-2xl">Админка сервиса</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">Вход по логину и паролю</p>
              </div>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="admin-username">Логин</Label>
                  <Input
                    id="admin-username"
                    autoComplete="username"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="admin-password">Пароль</Label>
                  <Input
                    id="admin-password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </div>
                {loginError && <p className="text-sm text-destructive">{loginError}</p>}
                <Button type="submit" className="w-full" disabled={loginLoading}>
                  {loginLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Shield className="mr-2 h-4 w-4" />}
                  Войти
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background px-4 py-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-col gap-4 border-b border-border/70 pb-5 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Shield className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">Админка сервиса</h1>
                <p className="text-sm text-muted-foreground">Аккаунт: {sessionUser}</p>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/">
              <Button variant="outline">На сайт</Button>
            </Link>
            <Button variant="ghost" onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              Выйти
            </Button>
          </div>
        </header>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <Card className="border-border/80 shadow-card">
            <CardHeader className="space-y-4">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Building2 className="h-5 w-5 text-primary" />
                  Компании
                </CardTitle>
                <form onSubmit={handleSearch} className="flex w-full gap-2 md:w-[25rem]">
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="УНП или название"
                    className="h-10"
                  />
                  <Button type="submit" size="icon" aria-label="Найти">
                    <Search className="h-4 w-4" />
                  </Button>
                </form>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">Всего: {total}</Badge>
                {appliedQuery && <Badge variant="outline">Поиск: {appliedQuery}</Badge>}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="overflow-x-auto rounded-lg border border-border/70">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-28">УНП</TableHead>
                      <TableHead>Компания</TableHead>
                      <TableHead>Статус</TableHead>
                      <TableHead>Дата регистрации</TableHead>
                      <TableHead>Адрес</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {companiesLoading && (
                      <TableRow>
                        <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                          <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                        </TableCell>
                      </TableRow>
                    )}
                    {!companiesLoading &&
                      companies.map((company) => (
                        <TableRow key={company.unp}>
                          <TableCell className="font-mono text-xs">{company.unp}</TableCell>
                          <TableCell className="min-w-[18rem] font-medium">
                            <Link to={`/company/${company.unp}`} className="hover:text-primary">
                              {company.name || company.short_name || "Без названия"}
                            </Link>
                          </TableCell>
                          <TableCell className="min-w-[10rem]">{company.status || "—"}</TableCell>
                          <TableCell className="whitespace-nowrap">{company.registration_date || "—"}</TableCell>
                          <TableCell className="min-w-[20rem] text-muted-foreground">{company.address || "—"}</TableCell>
                        </TableRow>
                      ))}
                    {!companiesLoading && companies.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                          Ничего не найдено
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>

              {companiesError && <p className="text-sm text-destructive">{companiesError}</p>}

              <div className="text-sm text-muted-foreground">
                Поиск использует основной быстрый индекс компаний. Для полной выгрузки загрузите файл с УНП справа.
              </div>
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="h-fit border-border/80 shadow-card">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <Clock3 className="h-5 w-5 text-primary" />
                    Источники данных
                  </CardTitle>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={loadDataSources}
                    disabled={dataSourcesLoading}
                    aria-label="Обновить источники данных"
                  >
                    {dataSourcesLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="overflow-x-auto rounded-lg border border-border/70">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Источник</TableHead>
                        <TableHead>Статус</TableHead>
                        <TableHead>Обновлен</TableHead>
                        <TableHead>Срез</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dataSourcesLoading && dataSources.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="h-20 text-center text-muted-foreground">
                            <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                          </TableCell>
                        </TableRow>
                      )}
                      {dataSources.map((source) => (
                        <TableRow key={source.key}>
                          <TableCell className="min-w-[13rem]">
                            <div className="font-medium text-foreground">{source.name}</div>
                            <div className="text-xs text-muted-foreground">
                              Записей: {source.records_count.toLocaleString("ru-RU")}
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={statusVariant(source.status)}>{statusLabel(source.status)}</Badge>
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-sm">{formatDateTime(source.updated_at)}</TableCell>
                          <TableCell className="whitespace-nowrap text-sm">{formatDate(source.source_date)}</TableCell>
                        </TableRow>
                      ))}
                      {!dataSourcesLoading && dataSources.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="h-20 text-center text-muted-foreground">
                            Источники данных пока не найдены
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
                {dataSourcesError && <p className="text-sm text-destructive">{dataSourcesError}</p>}
              </CardContent>
            </Card>

            <Card className="h-fit border-border/80 shadow-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <FileSpreadsheet className="h-5 w-5 text-primary" />
                  Файл по УНП
                </CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleFillFile} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="company-file">CSV или Excel</Label>
                    <Input
                      id="company-file"
                      type="file"
                      accept=".csv,.xlsx"
                      onChange={(event) => {
                        setSelectedFile(event.target.files?.[0] || null);
                        setFileError(null);
                        setFileMessage(null);
                      }}
                    />
                  </div>

                  {selectedFile && (
                    <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/40 px-3 py-2 text-sm">
                      <FileSpreadsheet className="h-4 w-4 text-primary" />
                      <span className="min-w-0 truncate">{selectedFile.name}</span>
                    </div>
                  )}

                  {fileError && <p className="text-sm text-destructive">{fileError}</p>}
                  {fileMessage && <p className="text-sm text-primary">{fileMessage}</p>}

                  <Button type="submit" className="w-full" disabled={fileLoading}>
                    {fileLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                    Заполнить и скачать
                  </Button>
                </form>

                <div className="mt-5 rounded-lg border border-border/70 bg-muted/35 p-3 text-sm text-muted-foreground">
                  <div className="mb-2 flex items-center gap-2 font-medium text-foreground">
                    <Download className="h-4 w-4 text-primary" />
                    Результат
                  </div>
                  <p>На выходе будет Excel-книга с листами по основным данным, историям и связанным реестрам.</p>
                </div>
              </CardContent>
            </Card>

            <Card className="h-fit border-border/80 shadow-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Database className="h-5 w-5 text-primary" />
                  Торговый реестр МАРТ
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                <form onSubmit={handleTradeRegistryImport} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="trade-registry-file">CSV торгового реестра</Label>
                    <Input
                      id="trade-registry-file"
                      type="file"
                      accept=".csv"
                      onChange={(event) => {
                        setTradeRegistryFile(event.target.files?.[0] || null);
                        setTradeRegistryError(null);
                      }}
                    />
                  </div>

                  {tradeRegistryFile && (
                    <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/40 px-3 py-2 text-sm">
                      <Database className="h-4 w-4 text-primary" />
                      <span className="min-w-0 truncate">{tradeRegistryFile.name}</span>
                    </div>
                  )}

                  {tradeRegistryError && <p className="text-sm text-destructive">{tradeRegistryError}</p>}

                  <div className="flex gap-2">
                    <Button type="submit" className="min-w-0 flex-1" disabled={tradeRegistryLoading}>
                      {tradeRegistryLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                      Загрузить
                    </Button>
                    <Button type="button" variant="outline" size="icon" onClick={loadTradeRegistryRuns} aria-label="Обновить статусы">
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  </div>
                </form>

                <div className="space-y-3">
                  {tradeRegistryRuns.map((run) => (
                    <div key={run.id} className="rounded-lg border border-border/70 bg-muted/35 p-3 text-sm">
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-medium text-foreground">{run.original_filename}</div>
                          <div className="text-xs text-muted-foreground">{run.source_date || "Дата не определена"}</div>
                        </div>
                        <Badge variant={statusVariant(run.status)}>{statusLabel(run.status)}</Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                        <span>Строк: {run.stats.rows ?? 0}</span>
                        <span>Записано: {run.stats.written ?? 0}</span>
                        <span>Компаний: {run.stats.matched ?? 0}</span>
                        <span>Из EGR: {run.stats.egr_saved ?? 0}</span>
                        <span>Пропущено: {run.stats.missing_unp_in_db ?? 0}</span>
                        <span>Дублей: {run.stats.duplicate_registry_keys ?? 0}</span>
                      </div>
                      {run.error && <p className="mt-2 text-xs text-destructive">{run.error}</p>}
                    </div>
                  ))}
                  {tradeRegistryRuns.length === 0 && (
                    <div className="rounded-lg border border-border/70 bg-muted/35 p-3 text-sm text-muted-foreground">
                      Импортов торгового реестра пока нет.
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    </div>
  );
};

export default Admin;
