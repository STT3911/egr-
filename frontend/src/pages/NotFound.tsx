import { Link } from "react-router-dom";
import { Header } from "@/components/layout/Header";
import { Button } from "@/components/ui/button";

const NotFound = () => {
  return (
    <div className="min-h-screen bg-background px-4 pb-12 pt-28">
      <Header />

      <div className="mx-auto flex min-h-[70vh] max-w-3xl items-center justify-center">
        <div className="surface-card rounded-[2rem] p-8 text-center shadow-card sm:p-12">
          <div className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
            404
          </div>
          <h1 className="mt-4 text-3xl font-extrabold text-foreground sm:text-4xl">
            Страница не найдена
          </h1>
          <p className="mt-3 text-base leading-7 text-muted-foreground">
            Проверьте адрес или вернитесь на главную страницу и начните поиск оттуда.
          </p>
          <Link to="/" className="mt-6 inline-flex">
            <Button>На главную</Button>
          </Link>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
