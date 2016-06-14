# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid
import json
import hashlib
from datetime import datetime, date
from collections import OrderedDict

import six
from django.forms import forms, formsets
from django.http.response import JsonResponse
from formtools.wizard.storage.exceptions import NoFileStorageConfigured
from formtools.wizard.views import NamedUrlWizardView


def default_json_serializer(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        serialized = obj.isoformat()
        return serialized
    raise TypeError("Type not serializable")


class WizardAPIView(NamedUrlWizardView):
    data_step_name = None
    new_step_name = None
    commit_step_name = None
    substep_separator = None
    json_serializer = None

    @classmethod
    def get_initkwargs(cls, form_list=None, initial_dict=None,
                       instance_dict=None, condition_dict=None, *args, **kwargs):
        """
        Creates a dict with all needed parameters for the form wizard instances

        * `form_list` - is a list of forms. The list entries can be single form
          classes or tuples of (`step_name`, `form_class`). If you pass a list
          of forms, the wizardview will convert the class list to
          (`zero_based_counter`, `form_class`). This is needed to access the
          form for a specific step.
        * `initial_dict` - contains a dictionary of initial data dictionaries.
          The key should be equal to the `step_name` in the `form_list` (or
          the str of the zero based counter - if no step_names added in the
          `form_list`)
        * `instance_dict` - contains a dictionary whose values are model
          instances if the step is based on a ``ModelForm`` and querysets if
          the step is based on a ``ModelFormSet``. The key should be equal to
          the `step_name` in the `form_list`. Same rules as for `initial_dict`
          apply.
        * `condition_dict` - contains a dictionary of boolean values or
          callables. If the value of for a specific `step_name` is callable it
          will be called with the wizardview instance as the only argument.
          If the return value is true, the step's form will be used.
        """

        kwargs.update({
            'initial_dict': initial_dict or kwargs.pop('initial_dict',
                                                       getattr(cls, 'initial_dict', None)) or {},
            'instance_dict': instance_dict or kwargs.pop('instance_dict',
                                                         getattr(cls, 'instance_dict', None)) or {},
            'condition_dict': condition_dict or kwargs.pop('condition_dict',
                                                           getattr(cls, 'condition_dict', None)) or {},
            'json_serializer': condition_dict or kwargs.pop('json_serializer',
                                                            getattr(cls, 'json_serializer',
                                                                    default_json_serializer)) or {},
            'data_step_name': kwargs.pop('data_step_name', 'data'),
            'commit_step_name': kwargs.pop('data_step_name', 'commit'),
            'substep_separator': kwargs.pop('substep_separator', '|'),
        })

        substep_separator = kwargs['substep_separator']

        form_list = form_list or kwargs.pop('form_list',
                                            getattr(cls, 'form_list', None)) or []

        computed_form_list = OrderedDict()

        assert len(form_list) > 0, 'at least one form is needed'

        # walk through the passed form list
        for i, form in enumerate(form_list):
            if isinstance(form, (list, tuple)):
                if isinstance(form[0], six.string_types):
                    step_name = six.text_type(form[0])
                    form_struct = form[1]
                else:
                    step_name = six.text_type(i)
                    form_struct = form

                assert substep_separator not in step_name

                if isinstance(form_struct, (list, tuple)):
                    # Handle substeps
                    for substep_name, substep_form in OrderedDict(form_struct).items():
                        assert substep_separator not in substep_name
                        computed_form_list['%s%s%s' % (
                            six.text_type(step_name),
                            substep_separator,
                            six.text_type(substep_name))
                        ] = substep_form
                else:
                    computed_form_list[six.text_type(step_name)] = form_struct
            else:
                # if not, add the form with a zero based counter as unicode
                computed_form_list[six.text_type(i)] = form

        # walk through the new created list of forms
        for form_struct in six.itervalues(computed_form_list):
            formset = []
            if isinstance(form_struct, dict):
                formset = (substep_form for _, substep_form in form_struct.items())
            elif issubclass(form_struct, formsets.BaseFormSet):
                # if the element is based on BaseFormSet (FormSet/ModelFormSet)
                # we need to override the form variable.
                formset = (form_struct.form,)
            # check if any form contains a FileField, if yes, we need a
            # file_storage added to the wizardview (by subclassing).
            for form in formset:
                for field in six.itervalues(form.base_fields):
                    if (isinstance(field, forms.FileField) and
                            not hasattr(cls, 'file_storage')):
                        raise NoFileStorageConfigured(
                            "You need to define 'file_storage' in your "
                            "wizard view in order to handle file uploads.")

        # build the kwargs for the wizardview instances
        kwargs['form_list'] = computed_form_list
        return kwargs

    def get(self, request, *args, **kwargs):
        """
        This renders the form or, if needed, does the http redirects.
        """
        step_url = kwargs.pop('step', self.steps.current)

        # is the current step the "data" name/view?
        if step_url == self.data_step_name:
            return self.render_state(current_step=self.storage.current_step)

        # is the url step name not equal to the step in the storage?
        # if yes, change the step in the storage (if name exists)
        elif step_url == self.steps.current:
            # URL step name and storage step name are equal, render!
            return self.render_state(current_step=step_url)

        elif step_url in self.get_form_list():
            self.storage.current_step = step_url
            return self.render_state(current_step=step_url)

        # invalid step name, reset to first and redirect.
        else:
            self.storage.current_step = self.steps.first
            kwargs['step'] = self.storage.current_step
            return self.get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        step = kwargs.pop('step', None)
        if step == self.commit_step_name:
            return self.commit_and_render_done(**kwargs)

        if not step in self.steps.all:
           return self.render_response_error('Missing required parameter "step"')

        # Update current step
        self.storage.current_step = step

        # get the form for the current step
        form = self.get_form(data=self.request.POST, files=self.request.FILES)

        # and try to validate
        if form.is_valid():
            # if the form is valid, store the cleaned data and files.
            self.storage.set_step_data(self.steps.current,
                                       self.process_step(form))
            self.storage.set_step_files(self.steps.current,
                                        self.process_step_files(form))

            # proceed to the next step, since the input was valid
            next_step = self.get_next_step(step=step)
            self.storage.current_step = next_step
            return self.render_state(current_step=next_step)

        # Return current step_data, since the data was invalid
        return self.render_state(current_step=step, form=form, status_code=400)

    def get_form_prefix(self, step=None, form=None):
        # Not using prefixes
        return ''

    def commit_and_render_done(self, **kwargs):
        """
        This method gets called when all forms passed. The method should also
        re-validate all steps to prevent manipulation. If any form fails to
        validate, `render_revalidation_failure` should get called.
        If everything is fine call `done`.
        """
        final_forms = OrderedDict()
        # walk through the form list and try to validate the data again.
        for form_key in self.get_form_list():
            form_obj = self.get_form(step=form_key,
                                     data=self.storage.get_step_data(form_key),
                                     files=self.storage.get_step_files(form_key))
            if not form_obj.is_valid():
                # Not all forms all valid: Fail Fast!
                return self.render_state(current_step=form_key, status_code=400)
            else:
                final_forms[form_key] = form_obj

        # render the done view and reset the wizard before returning the
        # response. This is needed to prevent from rendering done with the
        # same data twice.
        response = self.done(final_forms.values(), form_dict=final_forms, step=None)
        self.storage.reset()
        return response

    def render_form(self, step, form):
        return form.as_p()

    def render_preview(self, step, form):
        if form.is_bound and form.is_valid():
            data = form.cleaned_data
            return '<p>STEP: %s, DATA: %s</p>' % (step, json.dumps(data, default=self.json_serializer))
        return None

    def render_state(self, current_step, form=None, status_code=200):
        valid = self.is_valid()

        data = {
            'current_step': current_step if not valid else None,
            'done': valid,
            'structure': self.get_structure(),
            'steps': {}
        }

        for step in self.steps.all:
            current_form = None
            if form is not None and step == current_step:
                current_form = form
            data['steps'][step] = self.get_step_data(step=step, form=current_form)
        return JsonResponse(data, status=status_code)

    def render_response(self, data=None, status_code=200):
        data = data or {}
        return JsonResponse(data, status=status_code)

    def render_response_error(self, reason='', status_code=400, **kwargs):
        return JsonResponse(dict({'reason': reason}, **kwargs), status=status_code)

    def is_valid(self):
        valid = True
        for form_key in self.get_form_list():
            form_obj = self.get_form(step=form_key,
                                     data=self.storage.get_step_data(form_key),
                                     files=self.storage.get_step_files(form_key))
            if not form_obj.is_valid():
                valid = False
                break
        return valid

    def get_structure(self):
        return self.steps.all

    def get_step_data(self, step, form=None, empty=False):
        if form is None:
            form_data = self.storage.get_step_data(step) if not empty else None
            form_files = self.storage.get_step_files(step) if not empty else None

            form = self.get_form(step, data=form_data, files=form_files)

        return {
            'form_id': self.get_form_uuid(step),
            'form': self.render_form(step, form),
            'preview': self.render_preview(step, form),
            'valid': form.is_bound and form.is_valid(),
            'data': form.cleaned_data if (form.is_bound and form.is_valid()) else {}
        }

    def get_form_uuid(self, step):
        m = hashlib.md5()
        m.update(step.encode('utf-8'))
        return uuid.UUID(bytes=m.digest())
