class DuenioMixin:
    """Cada usuario solo ve y modifica sus propios registros; el administrador ve todo si admin_ve_todo."""
    campo_usuario = "usuario"
    admin_ve_todo = False
    throttle_scope = None      # las acciones de IA lo cambian a "ia" (@action(throttle_scope="ia"))

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if self.admin_ve_todo and u.es_administrador:
            return qs
        return qs.filter(**{self.campo_usuario: u})

    def perform_create(self, serializer):
        serializer.save(**{self.campo_usuario: self.request.user})
