from main.seo import page_context


def seo(request):
    return {'seo': page_context(request)}
