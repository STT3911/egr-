import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CompanySearch } from "@/components/CompanySearch";
import { Building2, BookOpen, TrendingUp, Database } from "lucide-react";

const Dashboard = () => {
  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-foreground mb-3">Панель управления ЕГР</h1>
          <p className="text-lg text-muted-foreground">
            Быстрый доступ к данным Единого государственного регистра
          </p>
        </div>

        {/* Search Section */}
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="w-5 h-5 text-primary" />
              Поиск компаний
            </CardTitle>
            <CardDescription>Введите УНП или название компании для быстрого поиска</CardDescription>
          </CardHeader>
          <CardContent>
            <CompanySearch 
              variant="compact"
              placeholder="Поиск по УНП или названию компании..."
            />
          </CardContent>
        </Card>

        {/* Quick Links */}
        <div className="grid gap-6 md:grid-cols-3">
          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                <BookOpen className="w-6 h-6 text-primary" />
              </div>
              <CardTitle>Справочники</CardTitle>
              <CardDescription>Коды ОПФ, ВЭД, статусов и другие справочники</CardDescription>
            </CardHeader>
            <CardContent>
              <Link to="/references">
                <Button variant="outline" className="w-full">Открыть справочники</Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                <Database className="w-6 h-6 text-primary" />
              </div>
              <CardTitle>База данных</CardTitle>
              <CardDescription>Статистика и информация о данных</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Компаний в БД:</span>
                  <span className="font-semibold">500K+</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Обновление:</span>
                  <span className="font-semibold">24/7</span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                <TrendingUp className="w-6 h-6 text-primary" />
              </div>
              <CardTitle>API Доступ</CardTitle>
              <CardDescription>Документация и примеры использования</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" className="w-full" disabled>
                Скоро доступно
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Recent Activity or Popular Searches could go here */}
      </div>
    </div>
  );
};

export default Dashboard;
