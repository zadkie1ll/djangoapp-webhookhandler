from django.shortcuts import render,get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pravburoProfile.models import Client, ClientOplata, ClientOplataSud, ClientOplataOther, NewClientStage
from django.contrib.auth.models import User, Group
from django.http import Http404
import requests
from datetime import datetime
import json
import re
import telebot
import os
from django.conf import settings





def Telegram_log(text):
    token = settings.TOKEN
    chat_id = '-1002256410940'
    bot = telebot.TeleBot(token)
    try:
        bot.send_message(chat_id, text)
    except Exception as e:
        return f'Error: {e}'


@csrf_exempt
def webhook_handler(request):
    if request.method == 'POST':
        data = request.POST
        document_id_2 = data.get('document_id[2]', None)

        if not document_id_2:
            return JsonResponse({'status': 'error', 'message': 'document_id[2] not found'}, status=400)

        deal_id_match = re.search(r'DEAL_(\d+)', document_id_2)
        if not deal_id_match:
            return JsonResponse({'status': 'error', 'message': 'Invalid deal ID format'}, status=400)
        deal_id = deal_id_match.group(1)

        deal_url = f"https://pravburo.bitrix24.ru/rest/33/cg7eb13y09rtqyxf/crm.deal.get.json?ID={deal_id}"
        response = requests.get(deal_url)
        if response.status_code != 200:
            return JsonResponse({'status': 'error', 'message': 'Failed to fetch deal data'}, status=response.status_code)

        try:
            deal_data = response.json().get('result', {})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON response'}, status=400)

        try:
            external_id = deal_data.get('CONTACT_ID')
            if not external_id:
                return JsonResponse({'status': 'error', 'message': 'External ID not found in deal data'}, status=400)

            external_url = f"https://pravburo.bitrix24.ru/rest/33/cg7eb13y09rtqyxf/crm.contact.get.json?ID={external_id}"
            external_response = requests.get(external_url)
            if external_response.status_code != 200:
                return JsonResponse({'status': 'error', 'message': 'Failed to fetch username'}, status=external_response.status_code)

            try:
                external_data = external_response.json()
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON response from external API'}, status=400)

            name_list = deal_data.get('TITLE').split()

            username = external_data.get('result', {}).get('PHONE', [{}])[0].get('VALUE', None)
            current_year = datetime.now().strftime("%Y")
            first_name = name_list[1]
            last_name = name_list[0]
            second_name = name_list[2]
            password = str(russian_to_translit(last_name) + current_year)

            if not User.objects.filter(username=username,first_name=first_name,last_name=last_name).exists():
                user = User.objects.create(
                username=username,
                first_name = first_name,
                last_name = last_name,
                
                )
                data = {
                            "fields": {
                                 "UF_CRM_1732014110700": f'{username}\n{password}',
                             }
                         }
                url = f'https://pravburo.bitrix24.ru/rest/33/n71ygr4i0x1o6c64/crm.deal.update.json?ID={deal_id}'
                response = requests.post(url, json=data)
                
                if response.status_code == 200:
                    user.set_password(password)
                    user.save()


                    my_group = Group.objects.get(name='clients_group')
                    my_group.user_set.add(user)
                    
                    sumall = int(deal_data.get('UF_CRM_1732785003047', 0).split('|')[0])
                    fully_paid = 0
                    sumoplachen = int(deal_data.get('UF_CRM_1732871209337', 0).split('|')[0])
                    if sumoplachen <=sumall:
                        fully_paid = 1
                    
                    if deal_data.get('UF_CRM_1732785067451', 0).split('|')[0] != '':
                        client = Client.objects.create(
                        user = user,
                        name = first_name,
                        middlename = second_name,
                        lastname = last_name,
                        sumall = sumall - int(deal_data.get('UF_CRM_1732785067451', 0).split('|')[0]),
                        discounted_price = sumall,
                        fully_paid = fully_paid,
                        sumplateg = deal_data.get('UF_CRM_1732785152659', 0).split('|')[0],
                        sumdate = str(datetime.fromisoformat(deal_data.get('UF_CRM_1732785182099', None)).date()),
                        sumoplachen = int(deal_data.get('UF_CRM_1732871209337', 0).split('|')[0]), 
                        datemounth = None,
                        datestartwork = datetime.fromisoformat(deal_data.get('UF_CRM_1732785118555', None)).date(),
                        ban = False,
                    )
                        
                    else:
                        client = Client.objects.create(
                        user = user,
                        name = first_name,
                        middlename = second_name,
                        lastname = last_name,
                        sumall = sumall,
                        fully_paid = fully_paid,
                        sumplateg = deal_data.get('UF_CRM_1732785152659', 0).split('|')[0],
                        sumdate = str(datetime.fromisoformat(deal_data.get('UF_CRM_1732785182099', None)).date()),
                        sumoplachen = int(deal_data.get('UF_CRM_1732871209337', 0).split('|')[0]), 
                        datemounth = None,
                        datestartwork = datetime.fromisoformat(deal_data.get('UF_CRM_1732785118555', None)).date(),
                        ban = False,
                        )
                        
                    text = f"Новый клиент из битрикса : {first_name} {second_name} {last_name}\nлогин от ЛК: {username}\nпароль от ЛК: {password}"
                    Telegram_log(text)
                    
                    new_client_stage = NewClientStage.objects.create(
                        client=client,
                        stage='Договор заключен',
                        date=datetime.now().strftime('%Y-%m-%d'),
                        description='Поздравляю, вы сделали первый шаг на пути к свободе от долгов!'
                    )
                    
                    data1 = {
                            "fields": {
                                 "UF_CRM_1733829783282": f"https://pravburo.bitrix24.ru/docs/path/Папки%20Клиентов/{client.lastname} {client.name} {client.middlename}"
                             }
                            }
                    url1 = f'https://pravburo.bitrix24.ru/rest/33/n71ygr4i0x1o6c64/crm.deal.update.json?ID={deal_id}'
                    response1 = requests.post(url1, json=data1)
                    
                    
                    data_disk = {
                                "id": "64575",
                                "data": {  
                                    "NAME": f"{client.lastname} {client.name} {client.middlename}"
                                    }
                                }

                    url = f'https://pravburo.bitrix24.ru/rest/33/lxptw8x3y2prn9m2/disk.folder.addsubfolder.json?'

                    response = requests.post(url, json=data_disk)

                    if response.status_code == 200:
                        response_json = response.json()
                        folder_id = response_json['result']['ID']
                        client.disk = folder_id
                        client.save()
                    else:
                        return f"Ошибка при запросе: {response.status_code}, {response.text}"
                    
                else:
                    return "Ошибка при обновлении поля:", response.text

            return JsonResponse({'status': 'success', 'message': 'Client and related data created or updated successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)




@csrf_exempt
def client_update_webhook_handler(request):
    if request.method == 'POST':
        data = request.POST
        document_id_2 = data.get('document_id[2]', None)

        if not document_id_2:
            return JsonResponse({'status': 'error', 'message': 'document_id[2] not found'}, status=400)

        deal_id_match = re.search(r'DEAL_(\d+)', document_id_2)
        if not deal_id_match:
            return JsonResponse({'status': 'error', 'message': 'Invalid deal ID format'}, status=400)
        deal_id = deal_id_match.group(1)

        deal_url = f"https://pravburo.bitrix24.ru/rest/33/cg7eb13y09rtqyxf/crm.deal.get.json?ID={deal_id}"
        response = requests.get(deal_url)
        if response.status_code != 200:
            return JsonResponse({'status': 'error', 'message': 'Failed to fetch deal data'}, status=response.status_code)

        try:
            deal_data = response.json().get('result', {})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON response'}, status=400)

        try:
            name_list = deal_data.get('TITLE').split()

            first_name = name_list[1]
            last_name = name_list[0]
            second_name = name_list[2]

            client = Client.objects.filter(
                name=first_name,
                middlename=second_name,
                lastname=last_name
            ).first()

            if not client:
                return JsonResponse({'status': 'error', 'message': 'Client not found'}, status=404)

            client.opredeleniesuda = 'https://esketit.com'

            client.save()

            return JsonResponse({'status': 'success', 'message': 'Client updated successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)


@csrf_exempt
def client_oplata_webhook_handler(request):
    if request.method == 'POST':
        data = request.POST
        document_id_2 = data.get('document_id[2]', None)

        if not document_id_2:
            return JsonResponse({'status': 'error', 'message': 'document_id[2] not found'}, status=400)

        deal_id_match = re.search(r'DEAL_(\d+)', document_id_2)
        if not deal_id_match:
            return JsonResponse({'status': 'error', 'message': 'Invalid deal ID format'}, status=400)
        deal_id = deal_id_match.group(1)

        deal_url = f"https://pravburo.bitrix24.ru/rest/33/cg7eb13y09rtqyxf/crm.deal.get.json?ID={deal_id}"
        response = requests.get(deal_url)
        if response.status_code != 200:
            return JsonResponse({'status': 'error', 'message': 'Failed to fetch deal data'}, status=response.status_code)

        try:
            deal_data = response.json().get('result', {})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON response'}, status=400)

        try:
            name_list = deal_data.get('TITLE').split()

            first_name = name_list[1]
            last_name = name_list[0]
            second_name = name_list[2]

            client = Client.objects.filter(
                name=first_name,
                middlename=second_name,
                lastname=last_name
            ).first()

            if not client:
                return JsonResponse({'status': 'error', 'message': 'Client not found'}, status=404)

            
            amount_oplata = deal_data.get('UF_CRM_1731501837650', 0)
            date_oplata = deal_data.get('UF_CRM_1731501853027', None)

            amount_sud = deal_data.get('UF_CRM_1731595327971', 0) 
            date_sud = deal_data.get('UF_CRM_1731595316907', None)

            amount_other = deal_data.get('UF_CRM_1731595352091', 0) 
            date_other = deal_data.get('UF_CRM_1731595340163', None)

            if amount_oplata != '' and date_oplata != None:
                amount1=int(amount_oplata)
                date1=datetime.fromisoformat(date_oplata).date()
                if not ClientOplata.objects.filter(client=client, date=date1, amount=amount1).exists():
                    ClientOplata.objects.create(
                        client=client,
                        amount=amount1,
                        date=date1
                    )
            if amount_sud != '' and date_sud != None:
                amount2=int(amount_sud)
                date2=datetime.fromisoformat(date_sud).date()
                if not ClientOplataSud.objects.filter(client=client, date=date2, amount=amount2).exists():
                    ClientOplataSud.objects.create(
                        client=client,
                        amount=amount2,
                        date=date2,
                        description="Оплата суда"
                    )

            if amount_other != '' and date_other != None:
                amount3=int(amount_other)
                date3=datetime.fromisoformat(date_other).date()
                if not ClientOplataOther.objects.filter(client=client, date=date3, amount=amount3).exists():
                    ClientOplataOther.objects.create(
                        client=client,
                        amount=amount3,
                        date=date3,
                        description="Другая оплата"
                    )

            return JsonResponse({'status': 'success', 'message': 'ClientOplata records created successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)
    
    
    

STAGE_DATA = {
        'C9:NEW':('Сбор документов', 'Юристы осуществляют сбор документов для дальнейшего анализа.'),
        'C9:PREPARATION':('Анализ ситуации', 'На основании полученных документов, юристы осуществляют анализ вашей ситуации.'),
        'C9:PREPAYMENT_INVOICE':('Анализ ситуации', 'На основании полученных документов, юристы осуществляют анализ вашей ситуации.'),
        'C9:UC_TCC6UZ':('Анализ ситуации', 'На основании полученных документов, юристы осуществляют анализ вашей ситуации.'),
        'C9:UC_8G8SGO':('Свяжитесь с сопровождающим юристом', 'Документы по вашему делу заблокированы, свяжитесь с сопровождающим юристом'),
        'C9:UC_W9NR7S':('Анализ ситуации', 'На основании полученных документов, юристы осуществляют анализ вашей ситуации.'),
        'C9:UC_2A99AW':('Анализ ситуации', 'На основании полученных документов, юристы осуществляют анализ вашей ситуации.'),
        'C9:UC_V6UB33':('Оплата депозита', 'Для подачи в суд оплатите депозит на реквизиты, которые можно получить у своего сопровождающего юриста.'),
        'C9:UC_ZU115F':('Подготовка заявления', 'Все документы собраны, ситуация проанализировна, депозит оплачен. По вашему делу готовится заявление в суд.'),
        'C9:FINAL_INVOICE':('Заявление в суде', 'Поздравляем, вы в суде! В ближайшее время вам присвоят индивидуальный номер дела.'),
        'C9:UC_UQTR9F':('Признание банкротом', 'Поздравляем, вы признаны банкротом! С этого дня вас официально не имеют право беспокоить приставы и коллекторы'),
        'C9:UC_E6XXFB':('Признание банкротом', 'Поздравляем, вы признаны банкротом! С этого дня вас официально не имеют право беспокоить приставы и коллекторы'),
        'C9:WON':('Долг списан','Процедура завершена. Поздравляем,  долги списаны! В ближайшее время вы получите судебное определение с подтверждением освобождения от долговых обязательств'),
        'C9:LOSE':('Свяжитесь с сопровождающим юристом','необходимо получить дополнительную информацию, свяжитесь с сопровождающим юристом'),
            }
@csrf_exempt
def client_change_handler(request):
    if request.method == 'POST':
        data = request.POST
        document_id_2 = data.get('document_id[2]', None)

        if not document_id_2:
            return JsonResponse({'status': 'error', 'message': 'document_id[2] not found'}, status=400)

        deal_id_match = re.search(r'DEAL_(\d+)', document_id_2)
        if not deal_id_match:
            return JsonResponse({'status': 'error', 'message': 'Invalid deal ID format'}, status=400)
        deal_id = deal_id_match.group(1)

        # Запрос данных сделки через API Битрикс24
        deal_url = f"https://pravburo.bitrix24.ru/rest/33/cg7eb13y09rtqyxf/crm.deal.get.json?ID={deal_id}"
        response = requests.get(deal_url)
        if response.status_code != 200:
            return JsonResponse({'status': 'error', 'message': 'Failed to fetch deal data'}, status=response.status_code)

        try:
            deal_data = response.json().get('result', {})
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON response'}, status=400)

        try:
            name_list = deal_data.get('TITLE').split()

            
            first_name = name_list[1]
            last_name = name_list[0]
            second_name = name_list[2]

            client = Client.objects.filter(
                name=first_name,
                middlename=second_name,
                lastname=last_name
            ).first()

            #СТАДИИ
            
            
            if not client:
                return JsonResponse({'status': 'error', 'message': 'Client not found'}, status=404)

            stage_id = deal_data.get('STAGE_ID', '')
            stage_info = STAGE_DATA.get(stage_id)
            
            if (stage_id != 'C3:UC_X52U3T') and (NewClientStage.objects.filter(stage='Свяжитесь с сопровождающим юристом').exists()):
                wrong_stage = NewClientStage.objects.filter(stage='Свяжитесь с сопровождающим юристом')
                wrong_stage.delete()

            if not stage_info:
                return JsonResponse({'status': 'error', 'message': f'Stage data not found for given stage_id {stage_id}'}, status=404)

            stage_name, description = stage_info
            date = datetime.now().date()  
            if not NewClientStage.objects.filter(client=client,stage=stage_name).exists():
                NewClientStage.objects.create(
                    client=client,
                    stage=stage_name,
                    date=date,
                    description=description
                )
            

            
            if not NewClientStage.objects.filter(stage='Присвоен номер дела').exists():
                if deal_data.get('UF_CRM_1731489410988') != '':
                    client.nomerdela = deal_data.get('UF_CRM_1720108289861')
                    client.nomerdelahref = deal_data.get('UF_CRM_1720108289861')
                    NewClientStage.objects.create(
                        client=client,
                        stage='Присвоен номер дела',
                        date=datetime.now().strftime('%Y-%m-%d'),
                        description=f'Документы переданы судье, на сайте суда можно отслеживать информацию по делу №{client.nomerdela}'
                        )
            client.opredeleniesuda = deal_data.get('UF_CRM_1731930829288')
                
            client.save() #НУЖНО СДЕЛАТЬ ДЛЯ СОПРОВОЖДЕНИЯ

            return JsonResponse({'status': 'success', 'message': 'NewClientStage record created successfully'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Only POST requests are allowed'}, status=405)
    
    
    
    


@csrf_exempt
def upload_documents(request):
    if request.method == 'POST':

        client_id = request.POST.get('client_id')
        if not client_id:
            return JsonResponse({'error': 'ID клиента не указан'}, status=400)

        client = get_object_or_404(Client, user__id=client_id)

        files = request.FILES.getlist('files[]')
        if not files:
            return JsonResponse({'error': 'Файлы не загружены'}, status=400)

        prepare_upload_url = 'https://pravburo.bitrix24.ru/rest/33/bchp6i8igcuqhkhl/disk.folder.uploadfile.json'

        results = [] 

        for file in files:
            original_name, file_extension = os.path.splitext(file.name)
            unique_name = f"{original_name}{file_extension}"


            file_data = {
                'id': client.disk,  
                'name': unique_name,  
            }

            try:
                prepare_response = requests.post(prepare_upload_url, data=file_data)

                if prepare_response.status_code != 200:
                    results.append({'file': file.name, 'status': 'error', 'message': 'Не удалось подготовить загрузку'})
                    continue

                prepare_response_json = prepare_response.json()
                upload_url = prepare_response_json['result'].get('uploadUrl')

                if not upload_url:
                    results.append({'file': file.name, 'status': 'error', 'message': 'Не удалось получить uploadUrl'})
                    continue

                with file.file as file_content:
                    upload_response = requests.post(upload_url, files={'file': (unique_name, file_content)})

                    if upload_response.status_code == 200:
                        upload_response_json = upload_response.json()
                        file_id = upload_response_json.get('ID')

                        if file_id:
                            print(f"Файл {file.name} успешно загружен как {unique_name}. ID файла: {file_id}")
                            results.append({'file': file.name, 'status': 'success', 'file_id': file_id})
                        else:
                            results.append({'file': file.name, 'status': 'error', 'message': 'ID файла не возвращен'})
                    else:
                        results.append({'file': file.name, 'status': 'error', 'message': upload_response.text})

            except Exception as e:
                results.append({'file': file.name, 'status': 'error', 'message': str(e)})

        return JsonResponse({'message': 'Обработка завершена', 'results': results})

    return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    
    
    
    
    
#БЫЛА ИДЕЯ СДЕЛАТЬ ВЬЮШКУ ДЛЯ ПРОСМОТРА ОПЛАТЫ, уже не  
def admin_oplata_view(request, client_id):
    client = get_object_or_404(Client, id=client_id)
    
    # Передаем клиента в шаблон
    return render(request, 'admin_oplata_view.html', {'client': client})
    
    
    
    
    
def russian_to_translit(text):
    translit_dict = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 
        'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 
        'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 
        'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 
        'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 
        'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 
        'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 
        'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z', 'И': 'I', 
        'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N', 
        'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 
        'У': 'U', 'Ф': 'F', 'Х': 'Kh', 'Ц': 'Ts', 'Ч': 'Ch', 
        'Ш': 'Sh', 'Щ': 'Shch', 'Ъ': '', 'Ы': 'Y', 'Ь': '', 
        'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    translit_text = ''.join(translit_dict.get(char, char) for char in text)
    return translit_text
    
    
    
    

def add_one_month(date_str):
    date_obj = datetime.fromisoformat(date_str)

    year = date_obj.year
    month = date_obj.month

    if month == 12:
        new_month = 1
        new_year = year + 1
    else:
        new_month = month + 1
        new_year = year

    if new_month in [1, 3, 5, 7, 8, 10, 12]:
        new_day = min(date_obj.day, 31)
    elif new_month in [4, 6, 9, 11]:
        new_day = min(date_obj.day, 30)
    else:

        if (new_year % 4 == 0 and new_year % 100 != 0) or (new_year % 400 == 0):
            new_day = min(date_obj.day, 29)
        else:
            new_day = min(date_obj.day, 28)

    new_date = datetime(new_year, new_month, new_day)

    return new_date.date()






    """amount_oplata = deal_data.get('UF_CRM_1731931257566', 0).split('|')[0]
            date_oplata = deal_data.get('UF_CRM_1731501853027', None)

            amount_sud = deal_data.get('UF_CRM_1731931356302', 0).split('|')[0] 
            date_sud = deal_data.get('UF_CRM_1731595316907', None)

            amount_other = deal_data.get('UF_CRM_1731595352091', 0).split('|')[0] 
            date_other = deal_data.get('UF_CRM_1731931376006', None)

            if amount_oplata != '' and date_oplata != None:
                if datetime.fromisoformat(date_oplata).date() != client.datestartwork:
                    amount1=int(amount_oplata)
                    date1=datetime.fromisoformat(date_oplata).date()
                    if not ClientOplata.objects.filter(client=client, date=date1, amount=amount1).exists():
                        ClientOplata.objects.create(
                            client=client,
                            amount=amount1,
                            date=date1
                        )
            if amount_sud != '' and date_sud != None:
                amount2=int(amount_sud)
                date2=datetime.fromisoformat(date_sud).date()
                if not ClientOplataSud.objects.filter(client=client, date=date2, amount=amount2).exists():
                    ClientOplataSud.objects.create(
                        client=client,
                        amount=amount2,
                        date=date2,
                        description="Оплата суда"
                    )

            if amount_other != '' and date_other != None:
                amount3=int(amount_other)
                date3=datetime.fromisoformat(date_other).date()
                if not ClientOplataOther.objects.filter(client=client, date=date3, amount=amount3).exists():
                    ClientOplataOther.objects.create(
                        client=client,
                        amount=amount3,
                        date=date3,
                        description="Другая оплата"
                    )"""
