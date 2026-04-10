import uuid

from django.conf import settings
from django.contrib import admin
from pymongo import MongoClient


def get_mongo_db():
    db_config = settings.DATABASES['default']
    if db_config.get('ENGINE') != 'djongo':
        raise RuntimeError('Djongo-safe admin helpers require the djongo backend.')

    db_name = db_config.get('NAME')
    db_host = db_config.get('CLIENT', {}).get('host')
    if not db_name or not db_host:
        raise RuntimeError('MongoDB connection settings are incomplete.')

    client = MongoClient(db_host)
    return client, client[db_name]


def _delete_related_documents(db, obj):
    for relation in obj._meta.related_objects:
        field = relation.field
        related_model = relation.related_model

        if relation.one_to_many or relation.one_to_one:
            db[related_model._meta.db_table].delete_many({field.attname: obj.pk})
            continue

        if relation.many_to_many and relation.auto_created:
            through = relation.through
            source_field_name = relation.field.m2m_reverse_field_name()
            source_field = through._meta.get_field(source_field_name)
            db[through._meta.db_table].delete_many({source_field.attname: obj.pk})


def delete_queryset_documents(queryset):
    client, db = get_mongo_db()
    try:
        collection = db[queryset.model._meta.db_table]
        for obj in queryset:
            _delete_related_documents(db, obj)
            collection.delete_many({'id': obj.pk})
    finally:
        client.close()


def sync_m2m_collection(instance, field_name, selected_objects):
    field = instance._meta.get_field(field_name)
    through = field.remote_field.through
    source_field = through._meta.get_field(field.m2m_field_name())
    target_field = through._meta.get_field(field.m2m_reverse_field_name())

    client, db = get_mongo_db()
    try:
        collection = db[through._meta.db_table]
        collection.delete_many({source_field.attname: instance.pk})

        documents = [
            {
                'id': uuid.uuid4(),
                source_field.attname: instance.pk,
                target_field.attname: selected_object.pk,
            }
            for selected_object in selected_objects
        ]
        if documents:
            collection.insert_many(documents)
    finally:
        client.close()


class DjongoSafeModelAdmin(admin.ModelAdmin):
    djongo_exclude_m2m = False

    def get_deleted_objects(self, objs, request):
        deleted_objects = [str(obj) for obj in objs]
        model_count = {self.model._meta.verbose_name_plural: len(deleted_objects)}
        return deleted_objects, model_count, set(), []

    def delete_model(self, request, obj):
        delete_queryset_documents(self.model._default_manager.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        delete_queryset_documents(queryset)

    def save_related(self, request, form, formsets, change):
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)

        for field in self.model._meta.many_to_many:
            if field.name in form.cleaned_data:
                sync_m2m_collection(form.instance, field.name, form.cleaned_data[field.name])